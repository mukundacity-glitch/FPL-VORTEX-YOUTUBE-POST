from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


try:
    from googleapiclient.errors import HttpError
    from httplib2 import HttpLib2Error
except ModuleNotFoundError:  # Offline data and repository contract tests.
    _HTTP_ERRORS = ()
else:
    _HTTP_ERRORS = (HttpError, HttpLib2Error)

DEFAULT_OUTPUT_ROOT = Path("/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO")
PACKAGE_NAME = "youtube_video_1_of_3_package.json"
REPORT_NAME = "youtube_private_upload.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_PRIVACY_STATUS = "private"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"Required {label} is missing or empty: {path}")
    return path


def _read_json(path: Path, label: str) -> dict[str, Any]:
    _required_file(path, label)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected {label} to contain a JSON object: {path}")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required GitHub secret: {name}")
    return value


def _oauth_value(youtube_name: str, google_name: str) -> str:
    value = (os.environ.get(youtube_name) or "").strip()
    if value:
        return value
    return _required_env(google_name)


def _safe_child(path_text: str, parent: Path, label: str) -> Path:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = parent / candidate
    candidate = candidate.resolve()
    if candidate.parent != parent.resolve():
        raise RuntimeError(f"{label} points outside {parent}: {candidate}")
    return _required_file(candidate, label)


def _upload_marker(preview_gw: int) -> str:
    return f"fpl-vortex-auto-gw{preview_gw:02d}-video-1-of-3"



def _official_season_identity(preview_gw: int) -> tuple[str, datetime]:
    """Derive a cross-season-safe video key from the LIVE official FPL deadline.

    A bare GW number repeats every season; blindly deduplicating GW10 would
    eventually suppress next year's legitimate video. Fail closed if official
    event identification is unavailable instead of guessing a season.
    """
    from urllib.request import Request, urlopen

    request = Request(
        "https://fantasy.premierleague.com/api/bootstrap-static/",
        headers={"User-Agent": "FPL-VORTEX-Day1/1.0"},
    )
    with urlopen(request, timeout=20) as response:
        bootstrap = json.load(response)
    events = bootstrap.get("events") or []
    event = next((e for e in events if int(e.get("id") or 0) == preview_gw), None)
    if not event or not event.get("deadline_time"):
        raise RuntimeError(
            f"Official FPL GW{preview_gw} deadline unavailable; cannot safely deduplicate."
        )
    deadline = datetime.fromisoformat(str(event["deadline_time"]).replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise RuntimeError("Official FPL deadline is not timezone aware")
    start_year = deadline.year if deadline.month >= 7 else deadline.year - 1
    return f"{start_year}-{start_year + 1}", datetime(start_year, 7, 1, tzinfo=timezone.utc)


def _find_existing_gameweek_video(youtube: Any, *, marker: str,
                                  legacy_marker: str,
                                  season_start: datetime,
                                  revision_tag: str | None = None,
                                  max_pages: int = 100) -> dict[str, str] | None:
    """Find an owned private draft for the requested gameweek and render revision.

    Legacy gameweek tags are matched against the official season start.
    Incomplete inventory checks fail before an upload can begin.
    """
    response = youtube.channels().list(part="contentDetails", mine=True).execute(num_retries=5)
    channels = response.get("items") or []
    if len(channels) != 1:
        raise RuntimeError("Cannot verify exactly one owned uploads playlist")
    uploads = ((channels[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    if not uploads:
        raise RuntimeError("Owner uploads playlist is unavailable; duplicate check blocked")
    token = None
    seen_tokens = set()
    for _ in range(max_pages):
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if token:
            params["pageToken"] = token
        page = youtube.playlistItems().list(**params).execute(num_retries=5)
        ids = [str((x.get("contentDetails") or {}).get("videoId") or "")
               for x in page.get("items") or []]
        ids = [x for x in ids if x]
        if ids:
            details = youtube.videos().list(part="snippet,status", id=",".join(ids)).execute(num_retries=5)
            videos = details.get("items") or []
            if {video.get("id") for video in videos} != set(ids):
                raise RuntimeError("YouTube omitted video details from the owner inventory; duplicate check blocked")
            for video in videos:
                snippet = video.get("snippet") or {}
                tags = set(snippet.get("tags") or [])
                matched = marker in tags
                if not matched and legacy_marker in tags:
                    published = str(snippet.get("publishedAt") or "")
                    try:
                        created = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    except ValueError:
                        # An unparseable date cannot establish the season;
                        # do not risk creating a duplicate private video.
                        raise RuntimeError("Legacy upload has no verifiable publication date")
                    matched = created >= season_start
                if matched:
                    privacy = str((video.get("status") or {}).get("privacyStatus") or "")
                    if privacy == YOUTUBE_PRIVACY_STATUS:
                        if revision_tag is None or revision_tag in tags:
                            return {"video_id": str(video["id"]), "privacy_status": privacy}
                        print(f"[YOUTUBE] Earlier Day 1 draft {video['id']} uses a different render revision.")
                        continue
                    if privacy not in {"public", "unlisted"}:
                        raise RuntimeError(
                            f"Cannot verify privacy of existing GW upload {video['id']}; "
                            "refusing duplicate-risk private upload"
                        )
                    # Preserve already published videos as-is, but keep scanning
                    # for an existing PRIVATE review copy before creating one.
                    print(f"[YOUTUBE] Existing GW video {video['id']} is {privacy}; "
                          "preserving publication and checking for a private draft.")
        token = page.get("nextPageToken")
        if not token:
            return None
        if token in seen_tokens:
            raise RuntimeError("YouTube uploads playlist repeated a page token; duplicate check blocked")
        seen_tokens.add(token)
    raise RuntimeError(
        f"Owner upload inventory exceeded {max_pages} pages; refuse duplicate-risk upload"
    )


def _validate_package(output_root: Path) -> dict[str, Any]:
    package_path = output_root / "DATA" / PACKAGE_NAME
    package = _read_json(package_path, "YouTube package")

    if package.get("manual_upload_only") is not False:
        raise RuntimeError("YouTube package is not enabled for automatic private upload")
    if package.get("youtube_api_upload_enabled") is not True:
        raise RuntimeError("YouTube API upload is not enabled in the package")
    if package.get("automatic_publication_enabled") is not False:
        raise RuntimeError("Automatic YouTube publication must remain disabled")

    policy = package.get("upload_policy")
    expected_policy = {
        "privacy_status": YOUTUBE_PRIVACY_STATUS,
        "notify_subscribers": False,
        "automatic_publish": False,
        "automatic_schedule": False,
        "manual_publication_required": True,
    }
    if policy != expected_policy:
        raise RuntimeError(
            f"YouTube private-upload policy mismatch: {policy!r} != {expected_policy!r}"
        )

    metadata = package.get("metadata")
    video = package.get("video")
    if not isinstance(metadata, dict):
        raise RuntimeError("YouTube package metadata is missing")
    if not isinstance(video, dict):
        raise RuntimeError("YouTube package video data is missing")

    preview_gw = int(metadata.get("preview_gw") or 0)
    review_gw = int(metadata.get("review_gw") or 0)
    if not 1 <= preview_gw <= 38 or not 1 <= review_gw <= 38:
        raise RuntimeError(
            f"Invalid dynamic Gameweeks: preview={preview_gw}, review={review_gw}"
        )
    if metadata.get("recommended_visibility") != "Private":
        raise RuntimeError("YouTube package visibility must be Private")
    if metadata.get("notify_subscribers_before_manual_publish") is not False:
        raise RuntimeError("Subscriber notifications must remain disabled")
    if metadata.get("made_for_kids") is not False:
        raise RuntimeError("Unexpected made-for-kids setting")
    if metadata.get("series") != {"part": 1, "total": 3}:
        raise RuntimeError("YouTube package must be VIDEO 1/3")

    title = str(metadata.get("title") or "").strip()
    description = str(metadata.get("description") or "").strip()
    tags = metadata.get("tags")
    category_id = str(metadata.get("category_id") or "").strip()
    language = str(metadata.get("language") or "").strip()
    if not title or len(title) > 100 or f"FPL GW{preview_gw}" not in title:
        raise RuntimeError("YouTube title is missing, too long, or has the wrong Gameweek")
    if not description or len(description.encode("utf-8")) > 5_000:
        raise RuntimeError("YouTube description is missing or too long")
    if not isinstance(tags, list) or not tags or not all(
        isinstance(tag, str) and tag.strip() for tag in tags
    ):
        raise RuntimeError("YouTube tags are missing or invalid")
    if category_id != "17" or not language:
        raise RuntimeError("YouTube Sports category or language is invalid")

    marker = _upload_marker(preview_gw)
    upload_tags = [str(tag).strip() for tag in tags]
    if marker not in upload_tags:
        upload_tags.append(marker)
    if sum(len(tag) for tag in upload_tags) + len(upload_tags) - 1 > 500:
        raise RuntimeError("YouTube tags exceed the 500-character limit")

    if re.search(r"\bDAY\s*\d", title, flags=re.IGNORECASE):
        raise RuntimeError("YouTube title must not use Day numbering")

    video_path = _safe_child(str(video.get("file") or ""), output_root / "MP4", "4K MP4")
    if list(video.get("resolution") or []) != [3840, 2160]:
        raise RuntimeError("YouTube upload package is not true 4K")

    revision = package.get("render_revision")
    current_revision = os.environ.get("GITHUB_SHA")
    if current_revision and revision != current_revision:
        raise RuntimeError("YouTube package does not belong to the current Day 1 run revision")
    if revision is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError("Invalid Day 1 render revision")
        with video_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != video.get("sha256"):
            raise RuntimeError("YouTube MP4 differs from the verified final Day 1 export")

    return {
        "render_revision": revision,
        "package_path": package_path,
        "video_path": video_path,
        "metadata": metadata,
        "upload_tags": upload_tags,
    }


def _youtube_service():
    refresh_token = _required_env("YOUTUBE_OAUTH_REFRESH_TOKEN")
    client_id = _oauth_value("YOUTUBE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _oauth_value("YOUTUBE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise RuntimeError("YouTube OAuth client ID has an invalid format")
    try:
        from google.auth.exceptions import RefreshError, TransportError
        from google.auth.transport.requests import Request as GoogleRequest
        from google_auth_httplib2 import AuthorizedHttp
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import build_http
    except ImportError as exc:
        raise RuntimeError(
            "YouTube upload dependencies are missing; install google-api-python-client "
            "and google-auth"
        ) from exc

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READ_SCOPE],
    )
    try:
        credentials.refresh(GoogleRequest())
    except RefreshError as exc:
        body = next((arg for arg in exc.args if isinstance(arg, dict)), {})
        reason = body.get("error")
        if reason in ("invalid_grant", "invalid_client", "invalid_scope", "unauthorized_client"):
            raise RuntimeError(f"YouTube OAuth rejected the refresh grant ({reason}). "
                               "Check the OAuth consent, scopes and GitHub secrets.") from None
        raise RuntimeError("YouTube OAuth refresh failed. Check the Google OAuth service and consent.") from None
    except TransportError:
        raise RuntimeError("YouTube OAuth refresh transport failed.") from None
    granted_scopes = set(credentials.granted_scopes or ())
    if granted_scopes:
        required_scopes = {YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READ_SCOPE}
        missing = required_scopes - granted_scopes
        if missing:
            raise RuntimeError(
                "YouTube refresh token is missing required OAuth scope(s): "
                + ", ".join(sorted(missing))
            )
    # Google's transport passes resumable 308 responses through to next_chunk().
    transport = AuthorizedHttp(credentials, http=build_http())
    return build("youtube", "v3", http=transport, cache_discovery=False)


def _verify_channel(youtube) -> dict[str, str]:
    expected_channel_id = _required_env("YOUTUBE_CHANNEL_ID")
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", expected_channel_id):
        raise RuntimeError("YOUTUBE_CHANNEL_ID has an invalid format")

    response = youtube.channels().list(
        part="id,snippet",
        mine=True,
        fields="items(id,snippet/title)",
    ).execute(num_retries=5)
    items = response.get("items") or []
    if len(items) != 1:
        raise RuntimeError(
            f"Expected OAuth to resolve exactly one YouTube channel; found {len(items)}"
        )
    item = items[0]
    channel_id = str(item.get("id") or "")
    channel_title = str(item.get("snippet", {}).get("title") or "")
    if channel_id != expected_channel_id:
        raise RuntimeError(
            "YouTube OAuth channel mismatch; refusing to upload. "
            f"expected={expected_channel_id}, authenticated={channel_id}"
        )
    return {
        "id": channel_id,
        "title": channel_title,
    }


def _insert_private_video(youtube, package: dict[str, Any]) -> str:
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("google-api-python-client is required for YouTube upload") from exc

    metadata = package["metadata"]
    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": package["upload_tags"],
            "categoryId": metadata["category_id"],
            "defaultLanguage": metadata["language"],
        },
        "status": {
            "privacyStatus": YOUTUBE_PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        str(package["video_path"]),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False,
    )
    response = None
    while response is None:
        progress, response = request.next_chunk(num_retries=5)
        if progress is not None:
            print(f"[YOUTUBE] Private upload progress: {progress.progress() * 100:.1f}%")
    video_id = str((response or {}).get("id") or "")
    if not video_id:
        raise RuntimeError("YouTube upload completed without a video ID")
    return video_id



def _confirm_private(youtube, video_id: str) -> None:
    for attempt in range(4):
        response = youtube.videos().list(
            part="status",
            id=video_id,
            fields="items(id,status(privacyStatus,uploadStatus,rejectionReason,failureReason))",
        ).execute(num_retries=5)
        items = response.get("items") or []
        if len(items) == 1 and items[0].get("id") == video_id:
            status = items[0].get("status") or {}
            actual = status.get("privacyStatus")
            if actual != YOUTUBE_PRIVACY_STATUS:
                raise RuntimeError(f"YouTube safety check failed: expected private, received {actual!r}")
            state = status.get("uploadStatus")
            if state in {"failed", "rejected", "deleted"}:
                raise RuntimeError(f"YouTube reports upload status {state} for {video_id}")
            if state not in {"uploaded", "processed"}:
                raise RuntimeError(f"YouTube returned an unknown upload status for {video_id}")
            print(f"[YOUTUBE] Verified private video; YouTube upload status: {state}.")
            return
        if attempt < 3:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("YouTube did not return the requested private video after upload; check its Studio status")


def _youtube_error(exc) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if not isinstance(status, int):
        if isinstance(exc, (RuntimeError, FileNotFoundError)):
            return str(exc)
        return type(exc).__name__
    try:
        body = json.loads(exc.content)
        errors = body.get("error", {}).get("errors", [])
        reason = errors[0].get("reason") if errors else None
    except (TypeError, ValueError, AttributeError):
        reason = None
    reason = reason if isinstance(reason, str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}", reason) else "unknown"
    if reason in {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}:
        return f"YouTube HTTP {status} ({reason}); check the project's quota and retry after its Pacific Time reset."
    if reason == "uploadLimitExceeded":
        return f"YouTube HTTP {status} ({reason}); the channel reached its upload limit. Check YouTube Studio."
    return f"YouTube HTTP {status} ({reason})"


def _upload_journal(remote, filename, row=None):
    """Persist intent before the insert so a lost response cannot trigger a second one."""
    def run(*args):
        result = subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(f"Day 1 upload journal Drive operation {args[0]} failed "
                               f"(rclone exit {result.returncode}); upload safety check blocked")
        return result.stdout

    if row is None:
        run("mkdir", remote)
        if filename not in run("lsf", "--files-only", "--max-depth", "1", remote).splitlines():
            return None
        record = json.loads(run("cat", f"{remote}/{filename}"))
        if not isinstance(record, dict) or record.get("status") not in {"upload_started", "video_created"}:
            raise RuntimeError("Day 1 upload journal is invalid; resolve it before starting another upload")
        return record

    with tempfile.TemporaryDirectory(prefix="day1-upload-") as folder:
        local = Path(folder) / filename
        _write_json_atomic(local, row)
        run("copyto", "--ignore-times", str(local), f"{remote}/{filename}")



def upload_private(output_root: Path) -> dict[str, Any]:
    output_root = output_root.resolve()
    return upload_day1_package(_validate_package(output_root), output_root / "DATA" / REPORT_NAME)


def upload_day1_package(package, report_path, *, hero=False):
    preview_gw = int(package["metadata"]["preview_gw"])
    expected_deadline = os.environ.get("VORTEX_DAY1_PREVIEW_DEADLINE")
    if expected_deadline and not hero:
        if str(preview_gw) != os.environ.get("VORTEX_DAY1_PREVIEW_GW"):
            raise RuntimeError("YouTube package preview Gameweek differs from preflight")
        if str(package["metadata"].get("review_gw")) != os.environ.get("VORTEX_DAY1_REVIEW_GW"):
            raise RuntimeError("YouTube package review Gameweek differs from preflight")
        deadline = datetime.fromisoformat(expected_deadline)
        if deadline <= datetime.now(timezone.utc):
            raise RuntimeError("Preview deadline passed before YouTube upload; regenerate the episode")
        start_year = deadline.year if deadline.month >= 7 else deadline.year - 1
        season_id = f"{start_year}-{start_year + 1}"
        season_start = datetime(start_year, 7, 1, tzinfo=timezone.utc)
    else:
        season_id, season_start = _official_season_identity(preview_gw)
    series = "player-hero" if hero else "video-1-of-3"
    marker = f"fpl-vortex-{season_id}-gw{preview_gw:02d}-{series}"
    legacy_marker = f"fpl-vortex-auto-gw{preview_gw:02d}-player-hero" if hero else _upload_marker(preview_gw)
    revision = package.get("render_revision")
    provisional_review = not hero and package["metadata"].get("review_status") == "LIVE/PARTIAL"
    revision_key = f"{revision or 'default'}-provisional" if provisional_review else revision
    revision_tag = f"fpl-vortex-day1-{revision_key}" if revision_key else None
    identity_tags = [marker, revision_tag] if revision_tag else [marker]
    package["upload_tags"] = list(dict.fromkeys(package["upload_tags"] + identity_tags))
    if len(",".join(package["upload_tags"])) > 500:
        raise RuntimeError("YouTube tags exceed the 500-character limit after adding Day 1 identifiers")
    report: dict[str, Any] = {
        "version": "FPL-VORTEX-YOUTUBE-PRIVATE-UPLOAD-V3",
        "preview_gw": preview_gw,
        "season_id": season_id,
        "deduplication_tag": marker,
        "render_revision": revision,
        "started_at": _utc_now(),
        "status": "starting",
        "package_file": str(package["package_path"]),
        "safety": {
            "requested_privacy_status": YOUTUBE_PRIVACY_STATUS,
            "notify_subscribers": False,
            "automatic_publish": False,
            "automatic_schedule": False,
            "manual_publication_required": True,
            "one_private_upload_per_season_gameweek_revision": True,
        },
    }
    _write_json_atomic(report_path, report)

    try:
        youtube = _youtube_service()
        channel = _verify_channel(youtube)
        report["channel"] = {"id": channel["id"], "title": channel["title"]}
        report["status"] = "channel_verified"
        _write_json_atomic(report_path, report)

        journal_remote = os.environ.get("VORTEX_DAY1_UPLOAD_JOURNAL")
        journal_name = f"{marker}-{revision_key or 'default'}.json"
        previous = _upload_journal(journal_remote, journal_name) if journal_remote else None
        existing = _find_existing_gameweek_video(
            youtube, marker=marker, legacy_marker=legacy_marker,
            season_start=season_start, revision_tag=revision_tag,
        )
        if previous and previous["status"] == "video_created":
            prior_id = previous.get("video_id")
            if not isinstance(prior_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", prior_id):
                raise RuntimeError("Day 1 upload journal has an invalid YouTube video ID")
            if existing and existing["video_id"] != prior_id:
                raise RuntimeError("YouTube inventory and the Day 1 upload journal identify different drafts")
            existing = {"video_id": prior_id, "privacy_status": YOUTUBE_PRIVACY_STATUS}
        if existing:
            video_id = existing["video_id"]
            _confirm_private(youtube, video_id)
            if journal_remote and previous and previous["status"] == "upload_started":
                _upload_journal(journal_remote, journal_name, {"status": "video_created", "video_id": video_id,
                                                               "at": _utc_now()})
            report.update({
                "status": "already_uploaded",
                "completed_at": _utc_now(),
                "duplicate_prevented": True,
                "youtube": {
                    "video_id": video_id,
                    "privacy_status": existing["privacy_status"],
                    "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
                    "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                },
            })
            _write_json_atomic(report_path, report)
            print("[YOUTUBE] Day 1 already uploaded for this season, gameweek and render revision.")
            return report

        if previous:
            raise RuntimeError(f"Unresolved prior YouTube upload attempt ({journal_name}). "
                               "Check the owner uploads in YouTube Studio before clearing the journal.")
        if journal_remote:
            _upload_journal(journal_remote, journal_name, {"status": "upload_started", "at": _utc_now()})
        print("[YOUTUBE] Uploading the current Day 1 render as PRIVATE.")
        video_id = _insert_private_video(youtube, package)
        if journal_remote:
            _upload_journal(journal_remote, journal_name, {"status": "video_created", "video_id": video_id,
                                                           "at": _utc_now()})
        report.update(
            {
                "status": "private_video_uploaded_verification_pending",
                "youtube": {
                    "video_id": video_id,
                    "privacy_status": YOUTUBE_PRIVACY_STATUS,
                    "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
                    "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                },
            }
        )
        _write_json_atomic(report_path, report)

        _confirm_private(youtube, video_id)
        report["status"] = "private_upload_complete"
        report["completed_at"] = _utc_now()
        report["duplicate_prevented"] = False
        _write_json_atomic(report_path, report)
        print("[YOUTUBE] PRIVATE 4K upload: PASS")
        print(f"[YOUTUBE] Studio: {report['youtube']['studio_url']}")
        print("[YOUTUBE] Automatic Public/Unlisted/scheduled publishing: DISABLED")
        return report
    except (*_HTTP_ERRORS, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report["status"] = "failed"
        report["failed_at"] = _utc_now()
        report["error"] = _youtube_error(exc)
        _write_json_atomic(report_path, report)
        raise RuntimeError(report["error"]) from None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upload the validated FPL VORTEX VIDEO 1/3 package to the verified "
            "YouTube channel as Private only"
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.environ.get("DAY1_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT)),
    )
    parser.add_argument("--check-credentials", action="store_true")
    args = parser.parse_args()
    if args.check_credentials:
        try:
            youtube = _youtube_service()
            _verify_channel(youtube)
        except (*_HTTP_ERRORS, RuntimeError, OSError) as exc:
            raise SystemExit(f"Day 1 YouTube credential check: {_youtube_error(exc)}") from None
        print("[YOUTUBE] OAuth grant and owned channel: PASS")
        return
    upload_private(args.output_root)


if __name__ == "__main__":
    main()


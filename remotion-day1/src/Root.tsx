import { Composition } from "remotion";
import { Day1Premium } from "./Composition";
import type { RenderProps } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Day1Premium"
      component={Day1Premium}
      width={3840}
      height={2160}
      fps={24}
      durationInFrames={24}
      defaultProps={{
        show: null,
        start: 0,
        end: 1,
        width: 3840,
        height: 2160,
        vertical: false,
        fontCss: "",
        verdictColors: {},
        popup: null,
      }}
      calculateMetadata={({ props }: { props: RenderProps }) => ({
        width: props.width,
        height: props.height,
        durationInFrames: Math.max(
          1,
          Math.ceil((props.end - props.start) * 24),
        ),
      })}
    />
  );
};

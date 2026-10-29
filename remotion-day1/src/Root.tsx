import { Composition } from "remotion";
import { Day1Premium } from "./Composition";
import type { RenderProps } from "./types";
import sample from "../sample-props.json";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Day1Premium"
      component={Day1Premium}
      width={1920}
      height={1080}
      fps={24}
      durationInFrames={9600}
      defaultProps={{
        show: sample.show,
        start: 0,
        end: 400,
        width: 1920,
        height: 1080,
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
          Math.ceil((props.end - props.start) * 24 - 1e-6),
        ),
      })}
    />
  );
};

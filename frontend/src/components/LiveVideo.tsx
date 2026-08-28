import Hls from "hls.js";
import { useEffect, useRef, useState } from "react";

interface Props {
  streamUrl: string;
  posterUrl?: string | null;
  onFailed?: () => void;
}

/** Plays a real HLS (.m3u8) live stream. Safari plays HLS natively; every
 * other browser needs hls.js's MediaSource-based implementation. Reports
 * failure (bad CORS headers, network error, unsupported browser) via
 * onFailed rather than showing a broken player, so callers can fall back to
 * a static snapshot image instead. */
export default function LiveVideo({ streamUrl, posterUrl, onFailed }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    setFailed(false);

    let hls: Hls | null = null;
    const fail = () => {
      setFailed(true);
      onFailed?.();
    };

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = streamUrl;
      video.addEventListener("error", fail);
    } else if (Hls.isSupported()) {
      hls = new Hls({ liveSyncDurationCount: 3, maxLiveSyncPlaybackRate: 1.2 });
      hls.loadSource(streamUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) fail();
      });
    } else {
      fail();
    }

    return () => {
      hls?.destroy();
      video.removeEventListener("error", fail);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamUrl]);

  if (failed) return null;

  return (
    <video
      ref={videoRef}
      autoPlay
      muted
      playsInline
      controls
      poster={posterUrl ?? undefined}
      onError={() => {
        setFailed(true);
        onFailed?.();
      }}
    />
  );
}

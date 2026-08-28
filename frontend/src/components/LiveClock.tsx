import { useEffect, useState } from "react";

// DC and VDOT's Northern Virginia coverage are both Eastern Time, so one
// timezone covers every real camera source in this app.
const formatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});

interface Props {
  prefix?: string;
}

/** A live-ticking local clock, so a real image/video is always shown next to
 * the actual current moment it represents -- not a stale or implied time. */
export default function LiveClock({ prefix = "As of" }: Props) {
  const [now, setNow] = useState(() => formatter.format(new Date()));

  useEffect(() => {
    const id = setInterval(() => setNow(formatter.format(new Date())), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span>
      {prefix} {now} ET
    </span>
  );
}

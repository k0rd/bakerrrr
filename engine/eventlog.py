"""Event log support for simulation-level events.

The log provides:
1. Player feedback
2. Debugging visibility
3. Emergent-behavior inspection
4. Replay-friendly history hooks
"""


class EventLog:

    def __init__(self, max_entries=200):

        self.entries = []
        self.max_entries = max_entries
        self.default_tick_source = None
        self.default_dedupe_window = 4
        self._next_sequence = 0
        self._recent_keys = {}

    def _normalize_tick(self, tick):
        if tick is None and callable(self.default_tick_source):
            try:
                tick = self.default_tick_source()
            except Exception:  # noqa: BLE001 - log metadata should never break logging
                tick = None
        if tick is None:
            return None
        try:
            return int(tick)
        except (TypeError, ValueError):
            return None

    def _normalize_priority(self, priority):
        if isinstance(priority, str):
            value = priority.strip().lower()
            if value == "low":
                return 0
            if value in {"high", "important"}:
                return 2
            if value in {"critical", "urgent"}:
                return 3
            return 1
        try:
            return max(0, int(priority))
        except (TypeError, ValueError):
            return 1

    def _normalized_segments(self, segments):
        if isinstance(segments, dict):
            text = segments.get("text")
            segments = segments.get("segments")
        else:
            text = None

        normalized = []
        plain = []
        for segment in segments or ():
            if not isinstance(segment, dict):
                continue
            seg_text = str(segment.get("text", ""))
            if not seg_text:
                continue
            normalized.append({
                "text": seg_text,
                "color": segment.get("color"),
                "attrs": int(segment.get("attrs", 0) or 0),
            })
            plain.append(seg_text)

        if text is None:
            text = "".join(plain)
        return normalized, str(text)

    def _make_entry(self, text, *, channel=None, priority=None, tick=None, segments=None):
        tick = self._normalize_tick(tick)
        entry = {
            "text": str(text),
            "channel": str(channel or "general").strip().lower() or "general",
            "priority": self._normalize_priority(priority),
            "tick": tick,
            "sequence": self._next_sequence,
        }
        if segments:
            entry["segments"] = segments
        return entry

    def _dedupe_key(self, entry, dedupe_key=None):
        text = str(dedupe_key if dedupe_key is not None else entry.get("text", ""))
        channel = str(entry.get("channel", "general") or "general").strip().lower()
        return channel, text

    def _dedupe_hit(self, entry, dedupe_window=None, dedupe_key=None):
        tick = entry.get("tick")
        if tick is None:
            return False
        if dedupe_window is None:
            dedupe_window = self.default_dedupe_window
        try:
            dedupe_window = int(dedupe_window)
        except (TypeError, ValueError):
            dedupe_window = 0
        if dedupe_window <= 0:
            return False

        key = self._dedupe_key(entry, dedupe_key=dedupe_key)
        previous = self._recent_keys.get(key)
        if not previous:
            return False

        previous_tick = previous.get("tick")
        if previous_tick is None:
            return False

        if tick - previous_tick > dedupe_window:
            return False

        entry_index = previous.get("index")
        if entry_index is None or entry_index < 0 or entry_index >= len(self.entries):
            return False

        refreshed = dict(self.entries.pop(entry_index))
        refreshed["repeat_count"] = int(refreshed.get("repeat_count", 1)) + 1
        refreshed["tick"] = tick
        refreshed["sequence"] = self._next_sequence
        refreshed["priority"] = max(int(refreshed.get("priority", 1) or 1), int(entry.get("priority", 1) or 1))
        refreshed["text"] = str(entry.get("text", refreshed.get("text", "")))
        if entry.get("segments"):
            refreshed["segments"] = entry["segments"]
        self.entries.append(refreshed)
        self._next_sequence += 1
        self._trim_recent_keys()
        self._recent_keys[key] = {"tick": tick, "index": len(self.entries) - 1}
        return True

    def _trim_recent_keys(self):
        valid = {}
        for index, entry in enumerate(self.entries):
            key = self._dedupe_key(entry)
            valid[key] = {
                "tick": entry.get("tick"),
                "index": index,
            }
        self._recent_keys = valid

    def _append(self, entry, *, dedupe_window=None, dedupe_key=None):
        if self._dedupe_hit(entry, dedupe_window=dedupe_window, dedupe_key=dedupe_key):
            return False

        self.entries.append(entry)
        self._recent_keys[self._dedupe_key(entry, dedupe_key=dedupe_key)] = {
            "tick": entry.get("tick"),
            "index": len(self.entries) - 1,
        }
        self._next_sequence += 1

        if len(self.entries) > self.max_entries:
            self.entries.pop(0)
            self._trim_recent_keys()

        return True

    def add(self, text, *, channel=None, priority=None, tick=None, dedupe_window=None, dedupe_key=None):
        entry = self._make_entry(
            text,
            channel=channel,
            priority=priority,
            tick=tick,
        )
        self._append(entry, dedupe_window=dedupe_window, dedupe_key=dedupe_key)

    def add_rich(
        self,
        segments,
        text=None,
        *,
        channel=None,
        priority=None,
        tick=None,
        dedupe_window=None,
        dedupe_key=None,
    ):
        normalized, entry_text = self._normalized_segments(segments)
        if text is not None:
            entry_text = str(text)
        entry = self._make_entry(
            entry_text,
            channel=channel,
            priority=priority,
            tick=tick,
            segments=normalized,
        )
        self._append(entry, dedupe_window=dedupe_window, dedupe_key=dedupe_key)

    def recent(self, n=10):

        return self.entries[-n:]

import threading
import time

EPOCH_MS = 1_704_067_200_000
APP_ID_BITS = 5
NODE_ID_BITS = 5
SEQUENCE_BITS = 12

MAX_APP_ID = (1 << APP_ID_BITS) - 1
MAX_NODE_ID = (1 << NODE_ID_BITS) - 1
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

NODE_ID_SHIFT = SEQUENCE_BITS
APP_ID_SHIFT = NODE_ID_SHIFT + NODE_ID_BITS
TIMESTAMP_SHIFT = APP_ID_SHIFT + APP_ID_BITS


class SnowflakeGenerator:
    def __init__(self, app_id: int, node_id: int) -> None:
        if not 0 <= app_id <= MAX_APP_ID:
            raise ValueError(f"app_id must be between 0 and {MAX_APP_ID}")
        if not 0 <= node_id <= MAX_NODE_ID:
            raise ValueError(f"node_id must be between 0 and {MAX_NODE_ID}")

        self.app_id = app_id
        self.node_id = node_id
        self._lock = threading.Lock()
        self._last_timestamp_ms = -1
        self._sequence = 0

    def next_id(self) -> int:
        with self._lock:
            timestamp_ms = self._timestamp_ms()

            if timestamp_ms < self._last_timestamp_ms:
                raise RuntimeError("system clock moved backwards")

            if timestamp_ms == self._last_timestamp_ms:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp_ms = self._wait_next_millisecond(timestamp_ms)
            else:
                self._sequence = 0

            self._last_timestamp_ms = timestamp_ms

            return (
                ((timestamp_ms - EPOCH_MS) << TIMESTAMP_SHIFT)
                | (self.app_id << APP_ID_SHIFT)
                | (self.node_id << NODE_ID_SHIFT)
                | self._sequence
            )

    def _wait_next_millisecond(self, timestamp_ms: int) -> int:
        next_timestamp_ms = self._timestamp_ms()
        while next_timestamp_ms <= timestamp_ms:
            next_timestamp_ms = self._timestamp_ms()
        return next_timestamp_ms

    @staticmethod
    def _timestamp_ms() -> int:
        return int(time.time() * 1000)


def extract_app_id(snowflake_id: int) -> int:
    return (snowflake_id >> APP_ID_SHIFT) & MAX_APP_ID


def extract_node_id(snowflake_id: int) -> int:
    return (snowflake_id >> NODE_ID_SHIFT) & MAX_NODE_ID

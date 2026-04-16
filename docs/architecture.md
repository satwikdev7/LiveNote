# LiveNote Architecture Notes

This repository follows the locked architecture defined for the LiveNote capstone:

- 15-second browser audio chunking
- 60-second intelligence cadence
- WebSocket-based live transport
- in-memory state during active meetings
- single active meeting per backend instance
- async diarization backfill in later phases

Phases 0-2 intentionally implement only the transport, state skeleton, and frontend session flow.


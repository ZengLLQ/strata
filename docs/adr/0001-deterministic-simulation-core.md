# ADR 0001: Deterministic Discrete-Event Simulation Core

## Status
Accepted

## Context
Strata requires a discrete-event simulation engine capable of deterministic execution.
In distributed systems research and fault testing, flaky simulations caused by non-deterministic tie-breaking, wall-clock coupling, floating-point drift, or unisolated random number generators undermine experiment validity.
Asyncio scheduling is non-deterministic with respect to simulated causality and message delivery order, making it unsuitable for core virtual-time event ordering.

## Decisions

### 1. Integer Microsecond Virtual Clock
- Virtual time is represented as a non-negative integer of virtual microseconds (`int`).
- Virtual time does not advance continuously; it steps discretely to the timestamp of the next event popped from the priority queue.
- Virtual time is completely decoupled from wall-clock time. Wall-clock time is recorded only for telemetry, diagnostic performance monitoring, and external timeout guards.

### 2. Priority Queue & Event Ordering Contract
Every event scheduled in the engine is assigned a tuple key:
```
(timestamp_us: int, priority: int, sequence_id: int)
```
- `timestamp_us`: Virtual time at which the event is scheduled to take effect.
- `priority`: Fixed integer priority tier:
  - `0`: System / Fault Events (crash, restart, partitions).
  - `1`: Node Lifecycle Transitions.
  - `2`: Network Message Delivery.
  - `3`: Workload Ingestion / Client Operations.
- `sequence_id`: A strictly monotonic integer incremented by the engine scheduler each time `schedule(...)` is called.

**Total Ordering Guarantee**:
If two events $E_1$ and $E_2$ have identical timestamps ($t_1 = t_2$) and identical priority ($p_1 = p_2$), the tie is broken strictly by their allocation sequence ID: $E_1 \prec E_2 \iff seq_1 < seq_2$. This establishes a strict total order over all scheduled events.

### 3. Seeded Randomness Boundary
- No module within the simulation engine may invoke Python's global `random` module or functions (`random.choice`, `random.random`, etc.).
- Every simulation instance owns a dedicated `random.Random(seed)` instance passed to stochastic subcomponents (network jitter, loss probability).
- The same experiment definition, engine version, and seed will generate an identical sequence of pseudo-random draws.

### 4. Node Lifecycle State Machine
Nodes exist in one of four mutually exclusive states:
- `INITIALIZING`: Node is created and registering handlers.
- `ONLINE`: Node is operational, processes incoming messages, and executes state machine updates.
- `OFFLINE`: Node is crashed; messages addressed to this node are dropped by the simulated network (or buffered if explicitly configured); node timers are halted.
- `RECOVERING`: Node is executing boot/recovery protocols before transitioning back to `ONLINE`.

### 5. Runaway Protection
The engine implements hard limits to guarantee termination:
- `max_virtual_time_us`: Ceiling on virtual time advancement.
- `max_events`: Maximum event iterations allowed.
- `wall_clock_timeout_seconds`: Guard against infinite loops inside user-defined event handlers.
Exceeding any threshold raises `RunawaySimulationError` or `SimulationTimeoutError`.

## Consequences
- Guaranteed reproducibility across runs on any platform.
- Zero reliance on external infrastructure or real sockets for the core simulation.
- Asynchronous boundaries (such as background file streaming or CLI tasks) wrap the simulation without dictating event order.

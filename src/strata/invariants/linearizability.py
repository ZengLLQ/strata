"""Formal sequential models and linearizability checking algorithms."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from strata.core.types import InvariantVerdict
from strata.invariants.base import BaseInvariant, InvariantResult
from strata.invariants.registry import InvariantRegistry
from strata.simulation.events import BaseEvent, WorkloadOperationEvent


@dataclass(frozen=True)
class OperationRecord:
    """Record of a concurrent client operation bounded by invocation and return timestamps."""

    client_id: str
    op_id: str
    op_type: str
    input_val: Any
    output_val: Any
    invoke_time_us: int
    return_time_us: int

    def __post_init__(self) -> None:
        if self.return_time_us < self.invoke_time_us:
            raise ValueError(
                f"return_time_us ({self.return_time_us}) cannot be earlier than invoke_time_us ({self.invoke_time_us})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "op_id": self.op_id,
            "op_type": self.op_type,
            "input_val": self.input_val,
            "output_val": self.output_val,
            "invoke_time_us": self.invoke_time_us,
            "return_time_us": self.return_time_us,
        }


@runtime_checkable
class SequentialModel(Protocol):
    """Protocol defining the sequential transition semantics of a shared object."""

    def initial_state(self) -> Any:
        """Return the immutable initial state of the object."""
        ...

    def step(
        self,
        state: Any,
        input_data: Any,
        expected_output: Any = ...,
    ) -> tuple[bool, Any, Any]:
        """Apply input_data to state.
        
        Returns:
            (is_valid, next_state, actual_output)
        """
        ...


class SequentialRegister:
    """Sequential specification for a single read/write register."""

    def __init__(self, initial_value: Any = None) -> None:
        self.initial_val = initial_value

    def initial_state(self) -> tuple[Any]:
        return (self.initial_val,)

    def step(
        self,
        state: tuple[Any],
        input_data: tuple[str, Any],
        expected_output: Any = ...,
    ) -> tuple[bool, tuple[Any], Any]:
        op_type, val = input_data
        curr_val = state[0]

        if op_type in ("write", "put"):
            next_state = (val,)
            actual_output = "ok"
            if expected_output is not ... and expected_output != actual_output:
                return False, state, actual_output
            return True, next_state, actual_output

        elif op_type in ("read", "get"):
            actual_output = curr_val
            if expected_output is not ... and expected_output != actual_output:
                return False, state, actual_output
            return True, state, actual_output

        return False, state, None


class SequentialKV:
    """Sequential specification for a multi-key dictionary store."""

    def initial_state(self) -> tuple[tuple[str, Any], ...]:
        return ()

    def step(
        self,
        state: tuple[tuple[str, Any], ...],
        input_data: tuple[str, str, Any],
        expected_output: Any = ...,
    ) -> tuple[bool, tuple[tuple[str, Any], ...], Any]:
        store = dict(state)
        op_type, key, val = input_data

        if op_type == "put":
            store[key] = val
            actual_output = val
            if expected_output is not ... and expected_output != actual_output:
                return False, state, actual_output
            next_state = tuple(sorted(store.items()))
            return True, next_state, actual_output

        elif op_type == "get":
            actual_output = store.get(key, None)
            if expected_output is not ... and expected_output != actual_output:
                return False, state, actual_output
            return True, state, actual_output

        return False, state, None


@dataclass(frozen=True)
class LinearizabilityCheckResult:
    """Outcome of linearizability search with linearization certificate or counterexample."""

    is_linearizable: bool
    linearized_sequence: list[OperationRecord]
    explanation: str
    details: dict[str, Any]


class LinearizabilityChecker:
    """Formal linearizability verification engine using bounded state-space exploration.
    
    Explores all valid topological interleavings of concurrent operations consistent
    with their real-time invocation and return boundaries.
    """

    def __init__(
        self,
        model: SequentialModel | None = None,
        max_search_depth: int = 50000,
    ) -> None:
        self.model: SequentialModel = model or SequentialKV()
        self.max_search_depth = max_search_depth

    def check(self, operations: Sequence[OperationRecord]) -> LinearizabilityCheckResult:
        """Check whether a concurrent history of operations is linearizable."""
        if not operations:
            return LinearizabilityCheckResult(
                is_linearizable=True,
                linearized_sequence=[],
                explanation="Empty operation history is trivially linearizable.",
                details={"operations_count": 0},
            )

        # Optimization: if model is SequentialKV, partition operations by key
        if isinstance(self.model, SequentialKV):
            return self._check_partitioned_kv(operations)

        # Standard monolithic search
        return self._search_linearization(list(operations), self.model)

    def _check_partitioned_kv(self, operations: Sequence[OperationRecord]) -> LinearizabilityCheckResult:
        """Partition KV operations by key and verify each partition independently."""
        key_buckets: dict[str, list[OperationRecord]] = {}
        for op in operations:
            key = op.input_val[0] if isinstance(op.input_val, (tuple, list)) else str(op.input_val)
            key_buckets.setdefault(key, []).append(op)

        all_linearized: list[OperationRecord] = []
        for key, key_ops in key_buckets.items():
            # Project onto single register model
            reg_model = SequentialRegister(initial_value=None)
            reg_ops = [
                OperationRecord(
                    client_id=o.client_id,
                    op_id=o.op_id,
                    op_type="write" if o.op_type == "put" else "read",
                    input_val=o.input_val[1] if isinstance(o.input_val, (tuple, list)) else o.input_val,
                    output_val="ok" if o.op_type == "put" else o.output_val,
                    invoke_time_us=o.invoke_time_us,
                    return_time_us=o.return_time_us,
                )
                for o in key_ops
            ]

            res = self._search_linearization(reg_ops, reg_model)
            if not res.is_linearizable:
                return LinearizabilityCheckResult(
                    is_linearizable=False,
                    linearized_sequence=[],
                    explanation=f"Linearizability violation detected on key '{key}': {res.explanation}",
                    details={"violating_key": key, **res.details},
                )
            # Map back to original ops
            op_map = {o.op_id: o for o in key_ops}
            all_linearized.extend([op_map[ro.op_id] for ro in res.linearized_sequence])

        # Sort the composite linearized sequence by invocation/return time
        all_linearized.sort(key=lambda op: (op.invoke_time_us, op.return_time_us))

        return LinearizabilityCheckResult(
            is_linearizable=True,
            linearized_sequence=all_linearized,
            explanation=f"All {len(operations)} operations across {len(key_buckets)} key partitions are linearizable.",
            details={"operations_count": len(operations), "key_partitions": list(key_buckets.keys())},
        )

    def _search_linearization(
        self,
        operations: list[OperationRecord],
        model: SequentialModel,
    ) -> LinearizabilityCheckResult:
        """Depth-first search with memoization exploring legal topological orderings."""
        n = len(operations)
        memo: set[tuple[Any, int]] = set()
        search_steps = 0

        # Precompute real-time precedence constraints:
        # op_a must precede op_b if op_a.return_time_us < op_b.invoke_time_us
        must_precede: list[int] = [0] * n
        for i in range(n):
            mask = 0
            for j in range(n):
                if i != j and operations[i].return_time_us < operations[j].invoke_time_us:
                    mask |= (1 << j)
            must_precede[i] = mask

        def dfs(curr_state: Any, completed_mask: int, path: list[OperationRecord]) -> list[OperationRecord] | None:
            nonlocal search_steps
            search_steps += 1
            if search_steps > self.max_search_depth:
                return None

            if completed_mask == (1 << n) - 1:
                return path

            memo_key = (curr_state, completed_mask)
            if memo_key in memo:
                return None

            # Find candidate operations eligible to execute next:
            # An operation i is eligible if it has not completed, and no uncompleted operation
            # was required to finish strictly before i started!
            for i in range(n):
                if not (completed_mask & (1 << i)):
                    # Check if any uncompleted op was strictly before i
                    # i requires that all ops with return_time < i.invoke_time are already completed
                    has_unmet_predecessor = False
                    for j in range(n):
                        if not (completed_mask & (1 << j)) and (operations[j].return_time_us < operations[i].invoke_time_us):
                            has_unmet_predecessor = True
                            break

                    if has_unmet_predecessor:
                        continue

                    # Try executing operation i
                    op = operations[i]
                    input_tuple = (op.op_type, op.input_val)
                    valid, next_state, _ = model.step(curr_state, input_tuple, expected_output=op.output_val)
                    if valid:
                        res = dfs(next_state, completed_mask | (1 << i), path + [op])
                        if res is not None:
                            return res

            memo.add(memo_key)
            return None

        init_state = model.initial_state()
        solution = dfs(init_state, 0, [])

        if solution is not None:
            return LinearizabilityCheckResult(
                is_linearizable=True,
                linearized_sequence=solution,
                explanation=f"Found valid linearization certificate of length {n} (searched {search_steps} states).",
                details={"search_steps": search_steps},
            )

        return LinearizabilityCheckResult(
            is_linearizable=False,
            linearized_sequence=[],
            explanation=(
                f"History of {n} operations is non-linearizable: no sequential execution "
                f"respecting real-time boundaries matches the sequential specification."
            ),
            details={"search_steps": search_steps, "operations_count": n},
        )


class LinearizableKVInvariant(BaseInvariant):
    """Evaluates whether all client KV operations satisfy strict linearizability."""

    def __init__(
        self,
        invariant_id: str = "inv_linearizability",
        description: str = "Client operations must be strictly linearizable against sequential specification",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            invariant_id=invariant_id,
            invariant_type="linearizability",
            description=description,
            parameters=parameters,
        )
        self.checker = LinearizabilityChecker(model=SequentialKV())

    def evaluate(self, engine: Any, events: Sequence[BaseEvent]) -> InvariantResult:
        """Extract workload operations and evaluate linearizability."""
        workload_events = [
            e for e in events
            if isinstance(e, WorkloadOperationEvent) or e.event_type == "workload.operation"
        ]

        if not workload_events:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.INCONCLUSIVE,
                explanation="No client operations were recorded during the experiment to verify linearizability.",
                relevant_event_ids=[],
                details={"operations_count": 0},
            )

        records: list[OperationRecord] = []
        for e in workload_events:
            payload = e.payload
            op_id = payload.get("operation_id", f"op_{e.sequence_id}")
            raw_op_type = payload.get("op_type", "get")
            op_type = "put" if raw_op_type in ("client_write", "put", "write") else "get"
            key = payload.get("key", "")
            val = payload.get("value")
            invoke_t = e.timestamp_us
            # Extract return time from extra payload or default to invoke_t + latency
            latency = payload.get("latency_us", 1000)
            return_t = payload.get("return_time_us", invoke_t + latency)

            records.append(
                OperationRecord(
                    client_id=e.source or "client",
                    op_id=op_id,
                    op_type=op_type,
                    input_val=(key, val) if op_type == "put" else (key, None),
                    output_val=val,
                    invoke_time_us=invoke_t,
                    return_time_us=return_t,
                )
            )

        check_res = self.checker.check(records)
        relevant_ids = [e.sequence_id for e in workload_events]

        if check_res.is_linearizable:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.PASSED,
                explanation=check_res.explanation,
                relevant_event_ids=relevant_ids,
                details={
                    "linearized_sequence": [op.to_dict() for op in check_res.linearized_sequence],
                    **check_res.details,
                },
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            invariant_type=self.invariant_type,
            verdict=InvariantVerdict.VIOLATED,
            explanation=check_res.explanation,
            relevant_event_ids=relevant_ids,
            details=check_res.details,
        )


# Automatically register LinearizableKVInvariant in the global registry
InvariantRegistry.register("linearizability", LinearizableKVInvariant)

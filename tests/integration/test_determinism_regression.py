"""Repeatability regression test verifying strict determinism across repeated seeded runs."""

from strata.core.experiment import (
    ExperimentDefinition,
    NetworkConfig,
    NetworkLinkConfig,
    TopologyConfig,
)
from strata.simulation.engine import DeterministicSimulationEngine


def test_determinism_identical_runs_produce_identical_histories(
    sample_experiment_def: ExperimentDefinition,
) -> None:
    """Contract: The same experiment definition and seed must produce identical event sequences.
    
    Verifies that sequence IDs, timestamps, priorities, sources, targets, and payloads
    are byte-for-byte identical across separate engine instances.
    """
    # Configure slight network jitter to exercise the stochastic RNG path
    exp_jittered = sample_experiment_def.model_copy(
        update={
            "topology": sample_experiment_def.topology.model_copy(
                update={
                    "network": NetworkConfig(
                        default_latency_us=1000,
                        default_jitter_us=200,  # [800us, 1200us]
                        default_drop_rate=0.0,
                    )
                }
            )
        }
    )

    # Run 1
    engine_1 = DeterministicSimulationEngine(experiment=exp_jittered, run_id="run_seeded_1")
    result_1 = engine_1.run()

    # Run 2
    engine_2 = DeterministicSimulationEngine(experiment=exp_jittered, run_id="run_seeded_2")
    result_2 = engine_2.run()

    # 1. High-level execution metrics equivalence
    assert result_1.events_processed == result_2.events_processed
    assert result_1.final_virtual_time_us == result_2.final_virtual_time_us
    assert result_1.all_invariants_passed == result_2.all_invariants_passed
    assert len(result_1.events) == len(result_2.events)

    # 2. Detailed event sequence comparison
    for idx, (e1, e2) in enumerate(zip(result_1.events, result_2.events)):
        assert e1.sequence_id == e2.sequence_id, f"Event {idx} sequence_id mismatch"
        assert e1.timestamp_us == e2.timestamp_us, f"Event {idx} timestamp mismatch"
        assert e1.priority == e2.priority, f"Event {idx} priority mismatch"
        assert e1.event_type == e2.event_type, f"Event {idx} event_type mismatch"
        assert e1.source == e2.source, f"Event {idx} source mismatch"
        assert e1.target == e2.target, f"Event {idx} target mismatch"
        assert dict(e1.payload) == dict(e2.payload), f"Event {idx} payload mismatch"

    # 3. Invariant results equivalence
    assert len(result_1.invariant_results) == len(result_2.invariant_results)
    for inv1, inv2 in zip(result_1.invariant_results, result_2.invariant_results):
        assert inv1.invariant_id == inv2.invariant_id
        assert inv1.verdict == inv2.verdict
        assert inv1.explanation == inv2.explanation
        assert inv1.relevant_event_ids == inv2.relevant_event_ids

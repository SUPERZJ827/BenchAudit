from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from benchcore.llm_auditor import BaseLLMAuditor


def test_llm_auditor_error_diagnostics_are_thread_local():
    auditor = BaseLLMAuditor(client=None)
    barrier = Barrier(2)

    def record(value: str) -> str | None:
        auditor.last_error = value
        barrier.wait(timeout=2)
        return auditor.last_error

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(record, "left-item-error")
        right = pool.submit(record, "right-item-error")

    assert {left.result(), right.result()} == {
        "left-item-error",
        "right-item-error",
    }

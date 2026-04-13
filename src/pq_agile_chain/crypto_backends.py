from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType


class BackendError(RuntimeError):
    """Raised when a PQ backend cannot be loaded or used."""


@dataclass(frozen=True, slots=True)
class SignatureBackend:
    algo_id: str
    module_path: str
    security_level: int
    display_name: str

    def _module(self) -> ModuleType:
        try:
            return import_module(self.module_path)
        except ModuleNotFoundError as exc:
            raise BackendError(
                "pqcrypto is required for PQ-Agile Chain. Install project dependencies first."
            ) from exc

    def generate_keypair(self) -> tuple[bytes, bytes]:
        module = self._module()
        public_key, secret_key = module.generate_keypair()
        return public_key, secret_key

    def sign(self, secret_key: bytes, message: bytes) -> bytes:
        return self._module().sign(secret_key, message)

    def verify(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        try:
            result = self._module().verify(public_key, message, signature)
        except Exception:
            return False
        return True if result is None else bool(result)


ALGORITHMS: dict[str, SignatureBackend] = {
    "ml-dsa-65": SignatureBackend(
        algo_id="ml-dsa-65",
        module_path="pqcrypto.sign.ml_dsa_65",
        security_level=3,
        display_name="ML-DSA-65",
    ),
    "sphincs-shake-256s-simple": SignatureBackend(
        algo_id="sphincs-shake-256s-simple",
        module_path="pqcrypto.sign.sphincs_shake_256s_simple",
        security_level=5,
        display_name="SPHINCS+-SHAKE-256s-simple",
    ),
}

DEFAULT_ALGO_ID = "ml-dsa-65"


def get_backend(algo_id: str) -> SignatureBackend:
    try:
        return ALGORITHMS[algo_id]
    except KeyError as exc:
        supported = ", ".join(sorted(ALGORITHMS))
        raise BackendError(
            f"Unsupported algorithm '{algo_id}'. Supported algorithms: {supported}"
        ) from exc


def security_level(algo_id: str) -> int:
    return get_backend(algo_id).security_level


def supported_algorithms() -> list[str]:
    return sorted(ALGORITHMS)

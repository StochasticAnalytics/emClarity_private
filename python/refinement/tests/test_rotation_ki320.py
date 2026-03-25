"""
Verification tests for KI-320: SPIDER ZYZ rotation matrix correctness.

KI-320 reported the rotation matrix multiplication order might be wrong.
Code analysis confirms it is correct: ``Rz(-phi) @ Ry(-theta) @ Rz(-psi)``
produces the inverse of the forward SPIDER ZYZ rotation
``Rz(psi) @ Ry(theta) @ Rz(phi)``.

These tests use angles **off symmetry axes** (5°, 50°, 95° — not 0°/45°/90°)
to prevent symmetry-axis masking of sign convention bugs.  At symmetry axes,
terms like sin(0)=0, cos(2*45)=0, sin(2*90)=0 vanish and can hide errors
in the rotation matrix construction.

Four test categories:
1. Comparison against scipy.spatial.transform.Rotation (independent impl)
2. Geometric vector tests with analytically known results
3. Orthogonality checks (det=1, R@R.T=I)
4. Round-trip: forward.T @ inverse = I
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from ..emc_tile_prep import spider_zyz_inverse_matrix

# Off-axis angle combinations that avoid symmetry zeros.
# Each tuple is (phi, theta, psi) in degrees.
OFF_AXIS_ANGLES = [
    (5.0, 50.0, 95.0),
    (95.0, 5.0, 50.0),
    (50.0, 95.0, 5.0),
    (-17.3, 63.7, 128.4),
    (143.0, 22.0, -67.5),
]


# ---------------------------------------------------------------------------
# Test 1: Compare against scipy.spatial.transform.Rotation
# ---------------------------------------------------------------------------


class TestSpiderZyzMatchesScipy:
    """spider_zyz_inverse_matrix matches scipy Rotation.from_euler('zyz').inv().

    SPIDER ZYZ forward rotation is ``Rz(psi) @ Ry(theta) @ Rz(phi)`` — note
    phi is applied *first* but appears rightmost in the matrix product.  This
    matches SciPy's **extrinsic** (lowercase) convention: ``from_euler('zyz',
    [phi, theta, psi])`` produces ``Rz(psi) @ Ry(theta) @ Rz(phi)``.

    The inverse of that forward rotation should match our function.
    """

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_matches_scipy(self, phi: float, theta: float, psi: float) -> None:
        """Our inverse matrix matches scipy's inverse at off-axis angles."""
        our_matrix = spider_zyz_inverse_matrix(phi, theta, psi)

        # SciPy extrinsic 'zyz': Rz(psi) @ Ry(theta) @ Rz(phi) = SPIDER fwd
        # Its inverse = our spider_zyz_inverse_matrix
        scipy_inv = (
            Rotation.from_euler("zyz", [phi, theta, psi], degrees=True)
            .inv()
            .as_matrix()
        )

        np.testing.assert_allclose(
            our_matrix, scipy_inv, atol=1e-10,
            err_msg=(
                f"Mismatch at phi={phi}, theta={theta}, psi={psi}. "
                f"Max diff: {np.max(np.abs(our_matrix - scipy_inv)):.2e}"
            ),
        )

    def test_identity_matches_scipy(self) -> None:
        """Zero angles produce identity in both implementations."""
        our_matrix = spider_zyz_inverse_matrix(0.0, 0.0, 0.0)
        scipy_inv = (
            Rotation.from_euler("zyz", [0.0, 0.0, 0.0], degrees=True)
            .inv()
            .as_matrix()
        )
        np.testing.assert_allclose(our_matrix, scipy_inv, atol=1e-15)
        np.testing.assert_allclose(our_matrix, np.eye(3), atol=1e-15)


# ---------------------------------------------------------------------------
# Test 2: Geometric vector tests with known analytical results
# ---------------------------------------------------------------------------


class TestRotationGeometricVectors:
    """Apply rotation matrices to known vectors and verify results analytically.

    These tests use exact-result angles (90° multiples) as positive controls,
    then verify off-axis angles produce geometrically sensible results.
    """

    def test_rz_neg90_maps_x_to_minus_y(self) -> None:
        """Rz(-90°) applied to [1,0,0] gives [0,-1,0].

        For psi=90, phi=theta=0: inverse is Rz(0)@Ry(0)@Rz(-90) = Rz(-90).
        Rz(-90) @ [1,0,0]^T = [cos(-90), sin(-90), 0] = [0, -1, 0].
        """
        rot = spider_zyz_inverse_matrix(0.0, 0.0, 90.0)
        v_in = np.array([1.0, 0.0, 0.0])
        v_out = rot @ v_in
        np.testing.assert_allclose(v_out, [0.0, -1.0, 0.0], atol=1e-10)

    def test_ry_neg90_maps_x_to_plus_z(self) -> None:
        """Ry(-90°) applied to [1,0,0] gives [0,0,+1].

        For theta=90, phi=psi=0: inverse is Rz(0)@Ry(-90)@Rz(0) = Ry(-90).
        Ry(-90) @ [1,0,0]^T = [cos(-90), 0, -sin(-90)] = [0, 0, 1].
        """
        rot = spider_zyz_inverse_matrix(0.0, 90.0, 0.0)
        v_in = np.array([1.0, 0.0, 0.0])
        v_out = rot @ v_in
        np.testing.assert_allclose(v_out, [0.0, 0.0, 1.0], atol=1e-10)

    def test_off_axis_preserves_vector_length(self) -> None:
        """Rotation preserves vector length for off-axis angles."""
        for phi, theta, psi in OFF_AXIS_ANGLES:
            rot = spider_zyz_inverse_matrix(phi, theta, psi)
            v_in = np.array([1.0, 2.0, 3.0])
            v_out = rot @ v_in
            np.testing.assert_allclose(
                np.linalg.norm(v_out),
                np.linalg.norm(v_in),
                atol=1e-12,
                err_msg=f"Length not preserved at ({phi}, {theta}, {psi})",
            )

    def test_off_axis_rotates_nontrivially(self) -> None:
        """Off-axis rotation actually changes the vector (not identity-like).

        At symmetry axes, some rotation components vanish.  Off-axis angles
        produce rotations where all 3 components of the output differ from
        the input (for a general input vector).

        Precondition: this check requires phi != 0 AND psi != 0 for each
        entry in OFF_AXIS_ANGLES.  With phi=0 or psi=0 the first Rz rotation
        is identity, leaving the x-component unchanged and making the y-
        component of the result zero — the assertion below would then fail
        even for a correct implementation.  This is a non-triviality check
        (the rotation is not near-identity), not a correctness check.
        """
        v_in = np.array([1.0, 0.0, 0.0])
        for phi, theta, psi in OFF_AXIS_ANGLES:
            rot = spider_zyz_inverse_matrix(phi, theta, psi)
            v_out = rot @ v_in
            # All 3 components should be non-zero for off-axis rotation of [1,0,0]
            assert np.all(np.abs(v_out) > 1e-6), (
                f"Rotation at ({phi}, {theta}, {psi}) produced near-zero "
                f"component: {v_out}"
            )


# ---------------------------------------------------------------------------
# Test 3: Orthogonality (det=1, R@R.T=I)
# ---------------------------------------------------------------------------


class TestRotationOrthogonality:
    """Verify rotation matrix properties: det(R)=1, R@R.T=I, R.T@R=I."""

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_determinant_is_one(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """det(R) = 1 (proper rotation, no reflection) at off-axis angles."""
        rot = spider_zyz_inverse_matrix(phi, theta, psi)
        assert np.linalg.det(rot) == pytest.approx(1.0, abs=1e-12), (
            f"det(R) = {np.linalg.det(rot):.15e} at ({phi}, {theta}, {psi})"
        )

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_r_rt_is_identity(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """R @ R.T = I at off-axis angles."""
        rot = spider_zyz_inverse_matrix(phi, theta, psi)
        np.testing.assert_allclose(
            rot @ rot.T, np.eye(3), atol=1e-12,
            err_msg=f"R@R.T != I at ({phi}, {theta}, {psi})",
        )

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_rt_r_is_identity(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """R.T @ R = I at off-axis angles."""
        rot = spider_zyz_inverse_matrix(phi, theta, psi)
        np.testing.assert_allclose(
            rot.T @ rot, np.eye(3), atol=1e-12,
            err_msg=f"R.T@R != I at ({phi}, {theta}, {psi})",
        )

    def test_orthogonality_random_angles(self) -> None:
        """Orthogonality holds for 50 random angle triples."""
        rng = np.random.default_rng(320)  # seed=320 for KI-320
        for _ in range(50):
            phi, theta, psi = rng.uniform(-180, 180, size=3)
            rot = spider_zyz_inverse_matrix(phi, theta, psi)
            np.testing.assert_allclose(
                rot @ rot.T, np.eye(3), atol=1e-12,
            )
            assert np.linalg.det(rot) == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Test 4: Round-trip (forward.T @ inverse = I)
# ---------------------------------------------------------------------------


class TestRotationRoundtrip:
    """Verify two distinct properties of the forward/inverse rotation pair.

    The forward SPIDER ZYZ rotation is Rz(psi) @ Ry(theta) @ Rz(phi).
    The inverse is Rz(-phi) @ Ry(-theta) @ Rz(-psi).

    Two separate properties hold (each tested independently):
      1. R_fwd.T == R_inv  — the inverse equals the transpose of the forward
         matrix (because R_fwd is orthogonal and R_inv is its algebraic
         inverse, which for orthogonal matrices equals the transpose).
      2. R_fwd @ R_inv = I — composing forward then inverse recovers identity
         (applies in both orders: R_fwd @ R_inv = I and R_inv @ R_fwd = I).

    Note: "R_forward.T @ R_inverse = I" is NOT a stated property here because,
    while numerically true (it reduces to R_inv @ R_inv = I only when
    R_fwd.T == R_inv), stating it as a single equation obscures the two
    underlying facts above.
    """

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_forward_transpose_equals_inverse(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """R_forward.T should equal R_inverse (they are the same matrix)."""
        r_inv = spider_zyz_inverse_matrix(phi, theta, psi)

        # Build forward rotation explicitly: Rz(psi) @ Ry(theta) @ Rz(phi)
        r_fwd = _build_forward_rotation(phi, theta, psi)

        np.testing.assert_allclose(
            r_fwd.T, r_inv, atol=1e-12,
            err_msg=(
                f"R_fwd.T != R_inv at ({phi}, {theta}, {psi}). "
                f"Max diff: {np.max(np.abs(r_fwd.T - r_inv)):.2e}"
            ),
        )

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_forward_times_inverse_is_identity(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """R_forward @ R_inverse = I (inverse undoes forward rotation)."""
        r_inv = spider_zyz_inverse_matrix(phi, theta, psi)
        r_fwd = _build_forward_rotation(phi, theta, psi)

        np.testing.assert_allclose(
            r_fwd @ r_inv, np.eye(3), atol=1e-12,
            err_msg=f"R_fwd @ R_inv != I at ({phi}, {theta}, {psi})",
        )

    @pytest.mark.parametrize(
        "phi, theta, psi",
        OFF_AXIS_ANGLES,
        ids=[f"phi={a[0]}_theta={a[1]}_psi={a[2]}" for a in OFF_AXIS_ANGLES],
    )
    def test_inverse_times_forward_is_identity(
        self, phi: float, theta: float, psi: float,
    ) -> None:
        """R_inverse @ R_forward = I (order independence for inverses)."""
        r_inv = spider_zyz_inverse_matrix(phi, theta, psi)
        r_fwd = _build_forward_rotation(phi, theta, psi)

        np.testing.assert_allclose(
            r_inv @ r_fwd, np.eye(3), atol=1e-12,
            err_msg=f"R_inv @ R_fwd != I at ({phi}, {theta}, {psi})",
        )

    def test_roundtrip_vector_recovery(self) -> None:
        """Rotating a vector forward then inverse recovers the original."""
        v_original = np.array([1.7, -0.3, 2.5])
        for phi, theta, psi in OFF_AXIS_ANGLES:
            r_inv = spider_zyz_inverse_matrix(phi, theta, psi)
            r_fwd = _build_forward_rotation(phi, theta, psi)

            v_rotated = r_fwd @ v_original
            v_recovered = r_inv @ v_rotated

            np.testing.assert_allclose(
                v_recovered, v_original, atol=1e-12,
                err_msg=f"Vector not recovered at ({phi}, {theta}, {psi})",
            )


# ---------------------------------------------------------------------------
# Helper: build forward rotation independently
# ---------------------------------------------------------------------------


def _build_forward_rotation(phi: float, theta: float, psi: float) -> np.ndarray:
    """Build the forward SPIDER ZYZ rotation: Rz(psi) @ Ry(theta) @ Rz(phi).

    This is an independent implementation that does NOT call
    ``spider_zyz_inverse_matrix``, ensuring the round-trip test is
    a genuine cross-check rather than a tautology.
    """
    phi_r = np.radians(phi)
    theta_r = np.radians(theta)
    psi_r = np.radians(psi)

    cphi, sphi = np.cos(phi_r), np.sin(phi_r)
    rz_phi = np.array([
        [cphi, -sphi, 0.0],
        [sphi, cphi, 0.0],
        [0.0, 0.0, 1.0],
    ])

    ctheta, stheta = np.cos(theta_r), np.sin(theta_r)
    ry_theta = np.array([
        [ctheta, 0.0, stheta],
        [0.0, 1.0, 0.0],
        [-stheta, 0.0, ctheta],
    ])

    cpsi, spsi = np.cos(psi_r), np.sin(psi_r)
    rz_psi = np.array([
        [cpsi, -spsi, 0.0],
        [spsi, cpsi, 0.0],
        [0.0, 0.0, 1.0],
    ])

    return rz_psi @ ry_theta @ rz_phi

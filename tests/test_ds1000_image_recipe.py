from pathlib import Path


def test_ds1000_image_recipe_covers_supported_execution_families() -> None:
    recipe = (
        Path(__file__).resolve().parents[1] / "docker" / "ds1000-audit" / "Dockerfile"
    ).read_text(encoding="utf-8")
    for requirement in ("numpy==1.24.4", "pandas==1.5.3", "scipy==1.10.1", "scikit-learn==1.2.2"):
        assert requirement in recipe
    assert "USER audit" in recipe

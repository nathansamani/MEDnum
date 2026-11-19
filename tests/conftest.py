import pytest

from mednum.synthetic import build_demo


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    """Jeu de données synthétique complet, généré une fois par session."""
    out = tmp_path_factory.mktemp("demo")
    build_demo(out)
    return out

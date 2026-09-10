import unittest
from pathlib import Path
from pipelines.image_pipeline.ingest import ImagePipeline
from pipelines.image_pipeline.extractors.preprocessor import ImagePreprocessor
from pipelines.image_pipeline.mock import get_mock_pipeline_result


def get_test_image_path() -> Path:
    sample_path = Path(__file__).parent / "samples" / "test.jpg"
    if sample_path.exists():
        return sample_path
    root_path = Path("test.jpg")
    if root_path.exists():
        return root_path
    return sample_path


def test_preprocessor():
    test_path = get_test_image_path()
    if test_path.exists():
        raw_bytes, name, size_kb, res = ImagePreprocessor.load_and_preprocess(test_path)
        assert len(raw_bytes) > 0
        assert size_kb > 0
        assert res[0] > 0 and res[1] > 0


def test_mock_result():
    res = get_mock_pipeline_result(image_name="test.jpg")
    assert res.metadata.source_image_name == "test.jpg"
    assert len(res.grounding_sources) == 7
    assert "NIST Cybersecurity Framework Benefits Advisory" in res.markdown_output
    assert "Provenance Table" in res.markdown_output
    assert "[^src-1]" in res.markdown_output


def test_pipeline_fallback():
    test_path = str(get_test_image_path())
    pipeline = ImagePipeline()
    res = pipeline.process(test_path, force_mock=True)
    assert res.mode == "mock"
    assert res.metadata.total_extracted_nodes == 7


class TestImagePipeline(unittest.TestCase):
    def test_preprocessor_case(self):
        test_preprocessor()

    def test_mock_result_case(self):
        test_mock_result()

    def test_pipeline_fallback_case(self):
        test_pipeline_fallback()


if __name__ == "__main__":
    unittest.main()

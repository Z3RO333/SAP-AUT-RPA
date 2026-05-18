from panels._panel_utils import result_failure_message


def test_result_failure_message_extracts_backend_errors():
    assert result_failure_message(
        {
            "status": "error",
            "errors": ["Nao foi possivel anexar ao SAP GUI."],
            "business_result": {},
        }
    ) == "Nao foi possivel anexar ao SAP GUI."


def test_result_failure_message_ignores_warning_results():
    assert result_failure_message(
        {
            "status": "warning",
            "errors": ["Ordem 123 falhou"],
            "business_result": {"results": [{"success": False}]},
        }
    ) == ""

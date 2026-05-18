from unittest.mock import Mock, patch

import pytest

from core.common.sap_session import NoSapSessionError, resolve_session


@patch("core.common.sap_session.get_session_by_ref", return_value=object())
@patch("core.common.sap_session._open_or_wait_for_manual_session")
@patch("core.common.sap_session._get_sap_server_env", return_value=None)
@patch("core.common.sap_session.list_sessions", return_value=[])
def test_resolve_session_waits_for_manual_login_when_sap_gui_has_no_sessions(
    _list_sessions_mock,
    _sap_server_mock,
    wait_manual_mock,
    _get_session_mock,
):
    wait_manual_mock.return_value = [{"session_ref": "0:0"}]

    _session, info = resolve_session(allow_manual_login=True)

    assert info["session_ref"] == "0:0"
    wait_manual_mock.assert_called_once_with()


@patch("core.common.sap_session.get_session_by_ref")
@patch("core.common.sap_session.list_sessions", return_value=[{"session_ref": "0:0"}])
def test_resolve_session_reports_stale_session_ref(_list_sessions_mock, _get_session_mock):
    with pytest.raises(NoSapSessionError, match="nao esta mais disponivel"):
        resolve_session(session_ref="0:1", allow_manual_login=True)

    _get_session_mock.assert_not_called()


@patch("core.common.sap_session.get_session_by_ref", return_value=object())
@patch("core.common.sap_session.auto_connect_to_server")
@patch("core.common.sap_session._get_sap_server_env", return_value="PRD")
@patch("core.common.sap_session.list_sessions", return_value=[])
def test_resolve_session_uses_configured_server_when_no_sessions(
    _list_sessions_mock,
    _sap_server_mock,
    auto_connect_mock,
    _get_session_mock,
):
    auto_connect_mock.return_value = [{"session_ref": "0:0"}]

    _session, info = resolve_session(allow_manual_login=True)

    assert info["session_ref"] == "0:0"
    auto_connect_mock.assert_called_once_with("PRD")

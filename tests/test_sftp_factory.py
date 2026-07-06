import pytest
from unittest.mock import MagicMock
from dcfs.app.sftp import create_sftp_server
from dcfs.app.sftp.handler import DCFSSFTPHandler

@pytest.mark.asyncio
async def test_sftp_factory_logic(mocker):
    # Mock dependencies
    clients = MagicMock()
    config = MagicMock()
    config.dcfs.sftp.host = '0.0.0.0'
    config.dcfs.sftp.port = 2022

    # Mock asyncssh.create_server to capture the factory
    mock_create_server = mocker.patch('asyncssh.create_server', mocker.AsyncMock())
    mocker.patch('asyncssh.read_private_key')
    mocker.patch('os.path.exists', return_value=True)

    await create_sftp_server(clients, config)

    # Get the sftp_factory from the call to create_server
    args, kwargs = mock_create_server.call_args
    sftp_factory = kwargs.get('sftp_factory')

    assert sftp_factory is not None

    # Simulate asyncssh calling sftp_factory(conn)
    mock_conn = MagicMock()
    handler_factory = sftp_factory(mock_conn)

    # It should return a callable (the handler factory)
    assert callable(handler_factory)

    # Simulate asyncssh calling handler_factory(chan)
    mock_chan = MagicMock()
    # We need to mock DCFSSFTPHandler because it calls super().__init__(chan)
    # which might try to do things with the mock_chan.
    # Actually, let's just see if it instantiates.

    # Mock SFTPServer.__init__ to avoid side effects
    mocker.patch('asyncssh.SFTPServer.__init__', return_value=None)

    handler = handler_factory(mock_chan)

    assert isinstance(handler, DCFSSFTPHandler)
    assert handler.clients == clients

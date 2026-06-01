"""Transparent at-rest encryption layer for DCFS.

This package provides a chunked, authenticated stream cipher that sits between
the high-level file API and the underlying Discord storage backend. When
enabled, all file content is encrypted client-side before being uploaded to
Discord channels, so that compromise of the channel or the metadata store
does not expose plaintext data.

Design summary:
  * Cipher:         AES-256-GCM (authenticated, hardware accelerated via AES-NI)
  * Chunk size:     64 KiB (configurable) -- enables random-access decryption
  * Per-file key:   HKDF-SHA256(master_key, salt=file_salt, info="dcfs-file-v1")
  * Master key:     Argon2id(passphrase, salt=master_salt) -- derived once on startup
  * File header:    60 bytes, inline at the start of the first Discord part,
                    so a file is self-describing and can be recovered even if the
                    DCFS metadata store is lost.

The encryption layer is implemented as a decorator around
``IFileContentRepository`` -- the rest of DCFS does not need to know whether
encryption is active.

Note: the heavyweight decorator class
``EncryptingFileContentRepository`` is *not* eagerly imported here, because
pulling it in would transitively load the Discord backend modules. Import
it explicitly when needed:

    from dcfs.crypto.repository import EncryptingFileContentRepository
"""

from dcfs.crypto.cipher import ChunkedAESGCM
from dcfs.crypto.header import FileHeader
from dcfs.crypto.kdf import derive_file_key, derive_master_key

__all__ = [
    "ChunkedAESGCM",
    "FileHeader",
    "derive_file_key",
    "derive_master_key",
]

.. _Installation:

Requirements
============

* A properly configured SSH agent for passwordless authentication
* OpenSSH client tools: ``ssh``, ``sshfs``, ``ssh-keyscan``, ``scp``
* Docker client tools: ``docker``
* [Mutagen](https://mutagen.io/documentation/introduction/installation/)


Installation
============

With uv

  .. code-block:: bash

    uv tool install dockerdo
    dockerdo install

With pip

  .. code-block:: bash

    pip install dockerdo
    dockerdo install

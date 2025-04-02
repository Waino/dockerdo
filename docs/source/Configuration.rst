.. _Configuration:

Configuration
=============

User configuration is in the ``~/.config/dockerdo/dockerdo.yaml`` file.

Example config:

.. code-block::

    always_record_inotify: false
    default_distro: ubuntu
    default_docker_registry: null
    default_image: ubuntu:latest
    default_remote_host: null
    ssh_key_path: /home/user/.ssh/id_rsa.pub

always_record_inotify
---------------------

Boolean. If True, then filesystem events are recorded even if you don't specify ``--record`` to ``dockerdo run``.

default_distro
--------------

The default distro of your dockerfiles, unless overridden with ``--distro`` in ``dockerdo init``.
The distro affects how ``sshd`` is installed.

default_docker_registry
-----------------------

The default docker registry to use, unless overridden with ``--registry`` in ``dockerdo init``.

default_image
-------------

The default base image, unless overridden with ``--image`` in ``dockerdo init``.

default_remote_host
-------------------

Use this remote host, unless overridden with ``--remote`` in ``dockerdo init``.

ssh_key_path
------------

Path to the ssh public key to install in the container.

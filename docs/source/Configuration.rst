.. _Configuration:

User Configuration
==================

User configuration is in the ``~/.config/dockerdo/dockerdo.yaml`` file.

Example config:

.. code-block::

    always_interactive: false
    always_record_inotify: false
    default_distro: ubuntu
    default_docker_registry: null
    default_docker_run_args: ''
    default_image: ubuntu:latest
    default_image_name_template: dockerdo-{base_image}:{base_image_tag}-{session_name}
    default_remote_delay: 0.3
    default_remote_host: null
    ssh_key_path: /home/user/.ssh/id_rsa.pub

always_interactive
------------------

Boolean. If True, then commands are always run in interactive mode, without needing to specify ``-i|--interactive``.
This comes at a performance penalty.

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

default_docker_run_args
-----------------------

The default arguments to pass to ``docker run``, unless turned off with ``--no-default-args`` in ``dockerdo run``.

default_image
-------------

The default base image, unless overridden with ``--image`` in ``dockerdo init``.

default_image_name_template
---------------------------

The template to use for the overlay image tag.
You can use the following variables:

* ``base_image``: the base image name, without the tag
* ``base_image_tag``: the base image tag
* ``session_name``: the session name

default_remote_delay
--------------------

The default delay to add to all remote commands, unless overridden with ``--remote-delay`` in ``dockerdo init``.

default_remote_host
-------------------

Use this remote host, unless overridden with ``--remote`` in ``dockerdo init``.

ssh_key_path
------------

Path to the ssh public key to install in the container.



Session Configuration
=====================

Session configuration is stored in the ``~/.local/share/dockerdo/${session_name}/session.yaml`` file for persistent sessions, and in a temporary directory for ephemeral sessions.

You can inspect the session configuration with ``dockerdo status``, or by editing the file directly.
You can modify some of the configuration variables after the session has been created, but not all of them.

base_image
----------

The base image that the overlay image is based on.
If you modify this, you must rerun ``dockerdo overlay`` and ``dockerdo build``.

container_name
--------------

The name of the container.
You can change this until you run the container, after which it is fixed.

container_state
---------------

The expected state of the container.
Modifying this will not change the state of the container.

container_username
------------------

The username to use in the container.
If you modify this, you must rerun ``dockerdo overlay`` and ``dockerdo build``.

distro
------

The distro of the base image.
If you modify this, you must rerun ``dockerdo overlay`` and ``dockerdo build``.

docker_registry
---------------

The docker registry to use.

docker_run_args
---------------

The arguments to pass to ``docker run``.

env
---

The environment variables to export to the container.

image_tag
---------

The tag of the overlay image.
Don't modify this value directly, instead rerun ``dockerdo build``.

local_work_dir
--------------

The working directory on the local host.

name
----

The name of the session.

record_inotify
--------------

Whether to record filesystem events.
You can change this until you run the container, after which it is fixed.

remote_delay
------------

The delay to add to all remote commands, to allow slow sshfs to catch up.
You can change this at any time, and the new value will affect future commands.

remote_host
-----------

The remote host to use.
This value should not be modified.

remote_host_build_dir
---------------------

The build directory on the remote host.
This value should not be modified.

session_dir
-----------

The session directory.
This value should not be modified.

ssh_port_on_remote_host
----------------------

The port on the remote host that the container ssh service will be published as.
The ``docker run`` command will receive a flag like ``-p ${ssh_port_on_remote_host}:22``.
The port doesn't need to be exposed through the firewall of the remote host, as we will jump through the sshd on the remote host.
You can change this until you run the container, after which it is fixed.

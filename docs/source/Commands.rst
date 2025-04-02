.. _Commands:

Commands
========

dockerdo install
^^^^^^^^^^^^^^^^

* Creates the dockerdo user configuration file (``~/.config/dockerdo/dockerdo.yaml``).
* Adds the dodo alias to your shell's rc file (``.bashrc``).
* Adds the dockerdo shell completion to ``.bashrc``.

dockerdo init
^^^^^^^^^^^^^

* Initializes a new session.
* Defines the work dir ``${WORK_DIR}`` on the local host.
* Mounts the remote host build directory using ``sshfs`` into ``${WORK_DIR}/${REMOTE_HOST}``.
* To activate the session in the current shell, use ``source $(dockerdo init)``.
  Later, you can use ``source ./local/share/dockerdo/${session_name}/activate`` to reactivate a persistent session.

dockerdo overlay
^^^^^^^^^^^^^^^^

* Creates ``Dockerfile.dockerdo`` which overlays a given image, making it dockerdo compatible.

    * Installs ``sshd``.
    * Copies your ssh key into ``authorized_keys`` inside the image.
    * Changes the CMD to start ``sshd`` and sleep forever.

* Supports base images using different distributions: ``--distro [ubuntu|alpine]``.

dockerdo build
^^^^^^^^^^^^^^

* Runs ``dockerdo overlay``, unless you already have a ``Dockerfile.dockerdo``.
* Runs ``docker build`` with the overlayed Dockerfile.
* Supports remote build with the ``--remote`` flag.
  Note that it is up to you to ensure that the Dockerfile is buildable on the remote host.

dockerdo push
^^^^^^^^^^^^^

* Only needed when the remote host is different from the local host.
* Pushes the image to the docker registry, if configured.
* If no registry is configured, the image is saved to a compressed tarball, copied to the remote host, and loaded.

dockerdo run
^^^^^^^^^^^^

* Starts the container on the remote host.
* Mounts the container filesystem using ``sshfs`` into ``${WORK_DIR}/container``.
* Accepts the arguments for ``docker run``.
* To record filesystem events, use ``dockerdo run --record &``.
  The command will continue running in the background to record events using inotify.

dockerdo export
^^^^^^^^^^^^^^^

* Add or overwrite an environment variable in the session environment.
* Never pass secrets this way.

dockerdo exec (alias dodo)
^^^^^^^^^^^^^^^^^^^^^^^^^^

* Executes a command in the running container.
* The working directory is deduced from the current working directory on the local host.
  E.g. if you ran ``dockerdo init`` in ``/home/user/project``, and are now in ``/home/user/container/opt/mysoftware``,
  the working directory on the container is ``/opt/mysoftware``.
* Note that you can pipe text in and out of the command, and the piping happens on the local host.

dockerdo status
^^^^^^^^^^^^^^^

* Prints the status of the session.

dockerdo stop
^^^^^^^^^^^^^

* Unmounts the container filesystem.
* Stops the container.

dockerdo history
^^^^^^^^^^^^^^^^

* Prints the command history of the session.
* Prints the list of modified files, if recording is enabled.

dockerdo rm
^^^^^^^^^^^

* Removes the container.
* Unmounts the remote host build directory.
* If you specify the ``--delete`` flag, the session directory is also deleted.

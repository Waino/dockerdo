===============
dockerdo / dodo
===============

.. image:: https://img.shields.io/pypi/v/dockerdo.svg
        :target: https://pypi.python.org/pypi/dockerdo

.. image:: https://readthedocs.org/projects/dockerdo/badge/?version=latest
        :target: https://dockerdo.readthedocs.io/en/latest/?version=latest
        :alt: Documentation Status


Use your local dev tools for remote docker development

If you love customizing your editor (nvim, emacs, anything goes) and your shell, then this is for you.

* Free software: MIT License
* Documentation: https://dockerdo.readthedocs.io.

Installation
------------

  .. code-block:: bash

    pip install dockerdo
    dockerdo install

Features
--------

* Uses ssh for remote execution, allowing seamless proxy jumps all the way from your local machine.
* Uses sshfs to make the container filesystem as easy to access as your local disk.

Concept
--------

The three systems
^^^^^^^^^^^^^^^^^

There are up to three systems ("machines") involved when using dockerdo.

* The **local host**: Your local machine (laptop, workstation) with your development tools installed.
* The **remote host**: The machine on which the Docker engine runs.
* The **container**: The environment inside the Docker container.

It's possible for the local and remote host to be the same machine, e.g. when doing local dockerfile development.

Use case: remote development
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you have ssh access to a compute cluster with much more resources than on your local laptop.
The cluster nodes have a basic linux environment, so your favorite dev tools are not installed.
Your dotfiles are not there, unless you copy them in to each node.
The lack of dotfiles means that your shell and editor dosn't behave the way you like.
It's best practice to containerize your workloads, instead of installing all your junk directly on the cluster node.
And naturally, inside the container there is only what was deemed necessary for the image, which can be even more sparse than the node.
Because the commands run in a shell on a remote machine, you can't use GUI tools (unless you do X11 forwarding, yuck).

Instead of putting all your tools and configuration in the container,
dockerdo makes the container transparently visible to your already configured local tools, including GUI tools.

Use case: Dockerfile development
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When writing a new Dockerfile, it is common to start a container from a base image and then begin installing software and changing configuration interactively in a shell on the container.
You then need to keep track of the final working commands and add them to the Dockerfile you are writing.
This can be a tedious workflow.

Dockerdo makes it a bit easier.
You can use your customized shell to move around, and your customized editor to write the files.
The ``dockerdo history`` command will list any files you modified, so that you can copy them to the repo to be used when building the Dockerfile.
The ``dockerdo history`` command will also list all the installation commands you executed, so you can copypaste into the Dockerfile.
Any local commands you run in between (``man``, ``diff``, ``grep``, ...) are not included in the history, making it easy to find the relevant commands.

Commands
--------

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

Configuration
-------------

User configuration is in the ``~/.config/dockerdo/dockerdo.yaml`` file.

Step-by-step example of ssh connections
---------------------------------------

Let's say your local host is called ``london``, and you want to use a remote host called ``reykjavik``.
The ``reykjavik`` host is listening on the normal ssh port 22.
We start a container, with sshd running on port 22 inside the container.
When starting the container, we give the ``-p 2222:22`` argument to ``docker run``, so that the container sshd is listening on port 2222 on the host.
However, the admins of ``reykjavik`` have blocked port 2222 in the firewall, so we can't connect directly.
We connect from ``london`` to ``reykjavik`` using port 22, and then jump to the container using port 2222 on ``reykjavik``.
Therefore, the ssh command looks like this:

.. code-block:: bash

    ssh -J reykjavik -p 2222 127.0.0.1

You have installed your key in ``~/.ssh/authorized_keys`` on ``reykjavik``, and ``dockerdo`` will copy it into the container.
Therefore, you can authenticate without a password both to ``reykjavik`` and the container.

If you need to configure a second jump host for ``reykjavik``, or any other ssh options, you should add it to the ssh config on ``london`` like you normally do.


Caveats
-------

* **There is no persistent shell environment in the container.**
  Instead, you must use the ``dockerdo export`` subcommand.
  Alternatively, you can set the variables for a particular app in a launcher script that you write and place in your image.

    * **Export** is the best approach when you need different values in different container instances launched from the same image,
      and when you need the env variables in multiple different programs. For example, setting the parameters of a benchmark.
    * **A launcher script** is the best approach when you have a single program that requires some env variables,
      and you always want to use the same values. Also the best approach if you have large amounts of data that you want to pass to the program through env variables.

* **``dockerdo history`` with recording will only list edits done via the sshfs mount.**
  Inotify runs on your local machine, and can only detect filesystem operations that happen locally.
  If you e.g. use your local editor to write a file on the sshfs mount, inotify will detect it.
  However, if a script inside the container writes a file, there is no way for inotify to detect it, because sshfs is not able to relay the events that it listens to from the container to the local host.

* **sshfs mount is not intended to replace docker volumes, you need both.**

    * Docker volumes/mounts are still needed for persisting data on the host, after the container is stopped and/or deleted.
      You only mount a specific directory, it doesn't make sense to have the entire container filesystem as a volume.
      Anything outside of the mounted volume is normally not easily accessible from the outside.
      Volumes often suffer from files owned by the wrong user (often root-owned files), due to mismatch in user ids between host and container.
    * The dockerdo sshfs mount spans the entire container filesystem. Everything is accessible.
      The files remain within the container unless copied out, making sshfs mounts unsuitable for persistent data storage.
      Sshfs doesn't suffer from weird file ownership.

* **git has some quirks with sshfs.**

    * You will have to set ``git config --global --add safe.directory ${GIT_DIR}`` to avoid git warnings.
      You don't need to remember this command, git will remind you of it.
    * Some git commands can be slower than normal.

* **Avoid --network=host in Docker.**
  If you need to use network=host in Docker, you have to run sshd on a different port than 22.
  The standard Dockerfile overlay will not do this for you.


Wouldn't it be nice
-------------------

Wouldn't it be nice if Docker integrated into the ssh ecosystem, allowing ssh into containers out-of-the box.

* ssh to the container would work similarly to docker exec shells.
* No need to install anything extra (sshd) in the containers, because the Docker daemon provides the ssh server.
* Keys would be managed in Docker on the host, instead of needing to copy them into the container.
* Env could be managed using Docker ``--env-file``, which would be cleaner.

Demo image
----------

Click to enlarge

.. image:: docs/source/demo.png
   :width: 100%

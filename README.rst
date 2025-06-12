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

Requirements
* A properly configured SSH agent for passwordless authentication
* OpenSSH client tools: ``ssh``, ``sshfs``, ``ssh-keyscan``, ``scp``
* Docker client tools: ``docker``
* [Mutagen](https://mutagen.io/documentation/introduction/installation/)

With uv

  .. code-block:: bash

    uv tool install dockerdo
    dockerdo install

With pip

  .. code-block:: bash

    pip install dockerdo
    dockerdo install

Features
--------

1. **Local Development Tools with Remote Power**:

   - Allows developers to use their customized local development environment (editors, shell, GUI tools) while working with containers on remote machines.
   - This solves the common problem of losing your preferred development setup when working on remote systems.

2. **SSH Integration**:

   - Uses standard SSH for remote execution
   - Supports SSH proxy jumps for complex network setups

3. **Transparent Filesystem Access**:

   - Uses SSHFS and Mutagen to mount container filesystems locally
   - Makes remote container files feel like they're on your local disk
   - Allows using local GUI tools to edit remote files: No need for X11 forwarding for GUI tools

4. **Port Forwarding**:

   - Supports port forwarding for services running in the container using Mutagen
   - Makes remote services feel like they're running locally

5. **Dockerfile Development Aid**:

   - Tracks file modifications and installation commands
   - `dockerdo history` command shows relevant commands for Dockerfile creation
   - Filters out local commands (like `man`, `diff`, `grep`) to keep history clean

6. **Ease of Use**:

   - Simple installation process (`uv` or `pip`)
   - Bash completion included
   - Supports different base distributions (Ubuntu, Alpine)
   - Can work with both local and remote Docker hosts

7. **Better response to latency**:

   - Over a slow connection, working normally over ssh causes user interface lag in the shell and TUI:
     it takes a moment for the remote host to respond to each keypress.
   - In a dockerdo workflow, feedback for keypresses is instant, as you are using the local shell and tools.
   - You still have to wait for commands to finish, but the user interface doesn't feel like molasses.

The tool is aimed towards developers who:

- Have heavily customized development environments
- Need to work with remote compute resources
- Want to maintain their workflow while using containers
- Need to develop and debug Dockerfiles

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
* Often you can skip this step, as ``dockerdo build`` will run it automatically.
  You need to run it manually if:

    * You want to inspect or modify the Dockerfile before building.
    * You want to recreate the Dockerfile with a different configuration.

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
* Always run this command in the background ``dockerdo run &``.
  The command will continue running in the background to maintain the master ssh connection.
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
* You can pipe text in and out of the command, and the piping happens on the local host.
* Note that stdin is only connected if you pipe text in, or you specify the ``-i/--interactive`` flag.

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
* Note: if ``dockerdo run`` fails and leaves the session in a bad state, you can use ``dockerdo rm --force`` to clean up.

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

* **git has some quirks with sshfs, use mutagen instead.**

    * The recommended workflow is to clone the repository on the local host, and then use mutagen to sync its contents to the container.
      Mutagen will sync the work directories (the content files), but not the metadata in the ``.git`` directory.
      This way, you can use your local git tools, and avoid the sshfs quirks.
    * If you need the full git repository including ``.git`` in the container, you can use sshfs. 
    * With sshfs, you will have to set ``git config --global --add safe.directory ${GIT_DIR}`` to avoid git warnings.
      You don't need to remember this command, git will remind you of it.
    * With sshfs, some git commands can be slower than normal.

* **Avoid --network=host in Docker.**
  If you need to use network=host in Docker, you have to run sshd on a different port than 22.
  The standard Dockerfile overlay will not do this for you.

* **On slow connections, sshfs / mutagen can sometimes be slower to update the filesystem than you can run ``dodo`` commands.**
  This can result in strange behavior, if you try to read the filesystem before it has been updated (e.g. files look empty or truncated).
  If this happens, have patience.
  You can use ``--remote_delay`` to help you have patience, by adding a delay to all remote commands:
  you can type as fast as you want, and the delay will be handled automatically for you.

* **A flag for interactive mode**

    * Note that stdin is only connected if you pipe text in, or you specify the ``-i/--interactive`` flag.
    * If you don't specify the flag and the command tries to read from stdin, you'll get an error, e.g. ``EOFError: EOF when reading a line``.
    * Interactive mode is slightly slower, as it has to work around a bug in ssh preventing the use of the master socket.


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

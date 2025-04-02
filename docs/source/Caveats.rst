.. _Caveats:

Caveats
=======

* **There is no persistent shell environment in the container.**
  Instead, you must use the ``dockerdo export`` subcommand.
  Alternatively, you can set the variables for a particular app in a launcher script that you write and place in your image.

    * **Export** is the best approach when you need different values in different container instances launched from the same image,
      and when you need the env variables in multiple different programs. For example, setting the parameters of a benchmark.
    * **A launcher script** is the best approach when you have a single program that requires some env variables,
      and you always want to use the same values. Also the best approach if you have large amounts of data that you want to pass to the  program through env variables.

* **``dockerdo history`` with recording will only list edits done via the sshfs mount.**
  Inotify runs on your local machine, and can only detect filesystem operations that happen locally.
  If you e.g. use your local editor to write a file on the sshfs mount, inotify will detect it.
  However, if a script inside the container writes a file, there is no way for inotify to detect it, because sshfs is not able to relay  the events that it listens to from the container to the local host.

* **sshfs mount is not intended to replace docker volumes, you need both.**

    * Docker volumes/mounts are still needed for persisting data on the host, after the container is stopped and/or deleted.
      You only mount a specific directory, it doesn't make sense to have the entire container filesystem as a volume.
      Anything outside of the mounted volume is normally not easily accessible from the outside.
      Volumes often suffer from files owned by the wrong user (often root-owned files), due to mismatch in user ids between host and     container.
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

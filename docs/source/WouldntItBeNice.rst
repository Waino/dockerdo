.. _WouldntItBeNice:

Wouldn't it be nice
===================

Wouldn't it be nice if Docker integrated into the ssh ecosystem, allowing ssh into containers out-of-the box.

* ssh to the container would work similarly to docker exec shells.
* No need to install anything extra (sshd) in the containers, because the Docker daemon provides the ssh server.
* Keys would be managed in Docker on the host, instead of needing to copy them into the container.
* Env could be managed using Docker ``--env-file``, which would be cleaner.

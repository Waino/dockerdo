.. _SshWalkthrough:

Step-by-step example of ssh connections
=======================================

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

If you need to configure a second jump host for ``reykjavik``, or any other ssh options, you should add it to the ssh config on          ``london`` like you normally do.

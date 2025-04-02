.. _Concept:

Concept
=======

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

When writing a new Dockerfile, it is common to start a container from a base image and then begin installing software and changing       configuration interactively in a shell on the container.
You then need to keep track of the final working commands and add them to the Dockerfile you are writing.
This can be a tedious workflow.

Dockerdo makes it a bit easier.
You can use your customized shell to move around, and your customized editor to write the files.                                         The ``dockerdo history`` command will list any files you modified, so that you can copy them to the repo to be used when building the    Dockerfile.
The ``dockerdo history`` command will also list all the installation commands you executed, so you can copypaste into the Dockerfile.
Any local commands you run in between (``man``, ``diff``, ``grep``, ...) are not included in the history, making it easy to find the     relevant commands.

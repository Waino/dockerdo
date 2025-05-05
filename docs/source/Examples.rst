.. _Examples:

Examples
========

Basic usage
-----------

.. image:: demo.png
   :width: 100%

This is the sequence shown in the demo figure.


.. code-block:: bash

    # Install only needs to be run once. I've already installed dockerdo, so using --dry-run here
    dockerdo install --dry-run

    # Initialize an ephemeral session
    source $(dockerdo init)

    # These are the defaults
    dockerdo status

    # Build calls overlay if needed
    dockerdo build

    # Local development: skipping push

    # Run should be backgrounded (but try --dry-run without & to see what happens)
    dockerdo run --record &

    # (screenshot)

    # Manage container env
    dockerdo export FOO=bar

    # Go to a directory in the container
    pushd container/home/ubuntu

    # `ls` runs in the container, but `tac` runs locally. Note: this stands in for a build or install command. Actual `ls` you would run     locally.
    dodo touch foo
    dodo ls -la | tac

    # `nvim` runs locally, editing a file on the container
    nvim configfile

    # Go outside the container mount point before stopping the container
    popd
    dockerdo stop

    # This output ought to be useful for writing your final Dockerfile (or maybe for writing a report on the experiment you ran in the       container)
    dockerdo history

    # And finally clean up
    dockerdo rm --delete
    deactivate_dockerdo   


Remote session with bells and whistles
--------------------------------------

.. code-block:: bash

    # Initialize a persistent session
    # We will build remotely on reykjavik
    source $(dockerdo init --remote reykjavik --distro alpine --image alpine:latest --user root --build-dir /tmp/build --container copenhagen --record --remote-delay 0.5 fancy_session)

    # Create the overlay Dockerfile
    dockerdo overlay

    # Edit/inspect the overlay Dockerfile
    nvim Dockerfile.dockerdo

    # Build the image remotely. Define the image tag manually
    dockerdo build --remote -t copenhagen:latest

    # Run the container remotely
    # Mount in a subdirectory of the remote host build dir
    mkdir reykjavik/persistent_storage
    dockerdo run -v ./persistent_storage:/persistent_storage &

    # Go to a directory in the container
    pushd container/root

    # Pipe both in and out
    ls -la | dodo tac | rev

    # Use an interactive command inside the container. Note: vim stands in for some interactive build command or experiment.
    dodo apk add vim
    dodo -i vim foo

    # Go outside the container mount point before stopping the container
    popd
    dockerdo stop

    # Restart the container
    dockerdo start &

    # Clean up with force
    dockerdo rm --force --delete
    deactivate_dockerdo

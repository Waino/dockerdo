.. refpapers documentation master file, created by
   sphinx-quickstart on Sat Feb 12 13:43:35 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to the documentation for dockerdo !
============================================

Source code on github: `<https://github.com/waino/dockerdo>`_

Documentation on readthedocs:  `<https://dockerdo.readthedocs.io/en/latest/?version=latest>`_

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Installation.rst
   Concept.rst
   Commands.rst
   Configuration.rst
   Examples.rst
   SshWalkthrough.rst
   WouldntItBeNice.rst
   Caveats.rst

Features
--------

* Uses ssh for remote execution, allowing seamless proxy jumps all the way from your local machine.
* Uses sshfs to make the container filesystem as easy to access as your local disk.
 
Demo image
----------

Click to enlarge

.. image:: demo.png
   :width: 100%


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

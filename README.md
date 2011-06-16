#mozremotebuilder
Regression finder that bisects on changesets, then builds changesets from moz-central using a remote server, downloads, and runs the built binaries interactively.

#implementation
mozremotebuilder sends requests to mozbuildserver, then waits on messages from mozilla pulse. mozbuildserver makes a commit to the mozilla tryserver for building.


#usage

	mozremotebisect -g [last good date] -b [bad date (default today)]

You can also use changesets instead of dates by setting -c flag to 1

	mozremotebisect -g [last good changeset] -b [bad changeset] -c 1

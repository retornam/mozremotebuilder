#mozremotebuilder
Regression finder that builds changesets from moz-central on a remote server

#usage

  mozremotebuild -g [last good date] -b [bad date (default today)]

You can also use changesets instead of dates by setting -c flag to 1

  mozremotebuild -g [last good changeset] -b [bad changeset] -c 1

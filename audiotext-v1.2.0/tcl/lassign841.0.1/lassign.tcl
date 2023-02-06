## -*- tcl -*-
# # ## ### ##### ######## ############# #####################

# Lassign. Forward compatibility support.

# I.e. code implementing a number of commands for 8.4 which are
# otherwise only defined in 8.5+

# # ## ### ##### ######## ############# #####################
## Requirements.

package require Tcl 8.4         ; # Minimum supported version.
package provide lassign84 1.0.1 ; # What we export.

# # ## ### ##### ######## ############# #####################
## I. Make sure that the Tcl interpreter has a 'lassign' command.

# Bail out if we are in an environment which already provides the
# command.
if {[llength [info commands ::lassign]]} return

# Command is missing, provide our emulation.
proc lassign {valueList args} {
    if {[llength $args] == 0} {
	return -code error "wrong # args: lassign list varname ?varname..?"
    }
    foreach v $args { uplevel 1 [list set $v {}] }
    uplevel 1 [list foreach $args $valueList {break}]
    return [lrange $valueList [llength $args] end]
}

##
# # ## ### ##### ######## ############# #####################
## Ready
return

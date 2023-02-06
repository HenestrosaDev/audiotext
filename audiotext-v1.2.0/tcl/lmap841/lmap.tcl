# -*- tcl -*-
##
# (c) 2017 Andreas Kupries http://wiki.tcl.tk/andreas%20kupries
#                               http://core.tcl.tk/akupries/
##
# Lmap. Forward compatibility support.

# I.e. code implementing a number of commands for 8.4 which are
# otherwise only defined in 8.5+

# # ## ### ##### ######## ############# #####################
## Requirements.

package require Tcl 8.4  ; # Minimum supported version.
package provide lmap84 1 ; # What we export.

# # ## ### ##### ######## ############# #####################
## I. Make sure that the Tcl interpreter has a 'lmap' command.

# Bail out if we are in an environment which already provides the
# command.
if {[llength [info commands ::lmap]]} return

# # ## ### ##### ######## #############
## Forward compatibility for lmap, conditional implementation

if {[package vsatisfies [package present Tcl] 8.5]} {
    # http://wiki.tcl.tk/40570
    # lmap forward compatibility
    # 8.5 - We have {*}

    proc lmap {args} {
	set body [lindex $args end]
	set args [lrange $args 0 end-1]
	set n 0
	set pairs [list]
	# Import all variables into local scope
	foreach {varnames listval} $args {
	    set varlist [list]
	    foreach varname $varnames {
		upvar 1 $varname var$n
		lappend varlist var$n
		incr n
	    }
	    lappend pairs $varlist $listval
	}
	# Run the actual operation via foreach
	set temp [list]
	foreach {*}$pairs {
	    lappend temp [uplevel 1 $body]
	}
	set temp
    }
} else {
    # Tcl 8.4. We do not have {*}.
    # Fall back to eval of a list (single command)

    proc lmap {args} {
	lappend cmd foreach
	set body [lindex $args end]
	set args [lrange $args 0 end-1]
	set n 0
	# Import all variables into local scope
	foreach {varnames listval} $args {
	    set varlist [list]
	    foreach varname $varnames {
		upvar 1 $varname var$n
		lappend varlist var$n
		incr n
	    }
	    lappend cmd $varlist $listval
	}
	# Run the actual operation via foreach
	lappend cmd { lappend temp [uplevel 1 $body] }
	set temp [list]
	eval $cmd
	set temp
    }
}

# # ## ### ##### ######## #############
return

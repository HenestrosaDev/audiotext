## -*- tcl -*-
# # ## ### ##### ######## ############# #####################

# Forward compatibility support for 'dict'.

# # ## ### ##### ######## ############# #####################
## Requirements.

package require Tcl 8.4 ; # Minimum supported version.
package provide dict84 1 ; # What we export.

# # ## ### ##### ######## ############# #####################
## II. Make sure that the Tcl interpreter has a 'dict' command.

# Bail out if we are in an environment which already provides the
# command.
if {[llength [info commands ::dict]]} return

# First try to get the separate 'dict' package first. It is C-based,
# i.e. faster, and ActiveTcl 8.4, for example, has it. Bail out if we
# had success, for we now have the necessary commands.

if {![catch {
    package require dict
}]} return

# Lastly use the poor man's dict -- a pure tcl [dict] emulation
# Very slow, but complete.
# Taken From http://wiki.tcl.tk/10609.
#
# Not all error checks are implemented!
# e.g. [dict create odd arguments here] will work
#
# Implementation is based on lists, [array set/get]
# and recursion

proc dict {cmd args} {
    uplevel 1 [linsert $args 0 _dict_$cmd]
}
proc _dict_get {dv args} {
    if {![llength $args]} {return $dv} else {
	array set dvx $dv
	set key [lindex $args 0]
	set dv $dvx($key)
	set args [lrange $args 1 end]
	return [eval [linsert $args 0 _dict_get $dv]]
    }
}
proc _dict_exists {dv key args} {
    array set dvx $dv
    set r [info exists dvx($key)]
    if {!$r} {return 0}
    if {[llength $args]} {
	return [eval [linsert $args 0 _dict_exists $dvx($key) ]]
    } else {return 1}
}
proc _dict_set {dvar key value args } {
    upvar 1 $dvar dv
    if {![info exists dv]} {set dv [list]}
    array set dvx $dv
    if {![llength $args]} {
	set dvx($key) $value
    } else {
	eval [linsert $args 0 _dict_set dvx($key) $value]
    }
    set dv [array get dvx]
}
proc _dict_unset {dvar key args} {
    upvar 1 $dvar mydvar
    if {![info exists mydvar]} {return}
    array set dv $mydvar
    if {![llength $args]} {
	if {[info exists dv($key)]} {
	    unset dv($key)
	}
    } else {
	eval [linsert $args 0 _dict_unset dv($key) ]
    }
    set mydvar [array get dv]
    return {}
}
proc _dict_keys {dv {pat *}} {
    array set dvx $dv
    return [array names dvx $pat]
}
proc _dict_append {dvar key args} {
    upvar 1 $dvar dv
    if {![info exists dv]} {set dv [list]}
    array set dvx $dv
    eval [linsert $args 0 append dvx($key) ]
    set dv [array get dvx]
}
proc _dict_create {args} {
    return $args
}
proc _dict_filter {dv ftype args} {
    set r [list]
    foreach {globpattern} $args {break}
    foreach {varlist script} $args {break}

    switch $ftype {
	key {
	    foreach {key value} $dv {
		if {[string match $globpattern $key]} {
		    lappend r $key $value
		}
	    }
	}
	value {
	    foreach {key value} $dv {
		if {[string match $globpattern $value]} {
		    lappend r $key $value
		}
	    }
	}
	script {
	    foreach {Pkey Pval} $varlist {break}
	    upvar 1 $Pkey key $Pval value
	    foreach {key value} $dv {
		if {[uplevel 1 $script]} {
		    lappend r $key $value
		}
	    }
	}
	default {
	    error "Wrong filter type"
	}
    }
    return $r
}
proc _dict_for {kv dict body} {
    uplevel 1 [list foreach $kv $dict $body]
}
proc _dict_incr {dvar key {incr 1}} {
    upvar 1 $dvar dv
    if {![info exists dv]} {set dv [list]}
    array set dvx $dv
    if {![info exists dvx($key)]} {set dvx($key) 0}
    incr dvx($key) $incr
    set dv [array get dvx]
}
proc _dict_info {dv} {
    return "Dictionary is represented as plain list"
}
proc _dict_lappend {dvar key args} {
    upvar 1 $dvar dv
    if {![info exists dv]} {set dv [list]}
    array set dvx $dv
    eval [linsert $args 0 lappend dvx($key)]
    set dv [array get dvx]
}
proc _dict_merge {args} {
    foreach dv $args {
	array set dvx $dv
    }
    array get dvx
}
proc _dict_replace {dv args} {
    foreach {k v} $args {
	_dict_set dv $k $v
    }
    return $dv
}
proc _dict_remove {dv args} {
    foreach k $args {
	_dict_unset dv $k
    }
    return $dv
}
proc _dict_size {dv} {
    return [expr {[llength $dv]/2}]
}
proc _dict_values {dv {gp *}} {
    set r [list]
    foreach {k v} $dv {
	if {[string match $gp $v]} {
	    lappend r $v
	}
    }
    return $r
}
proc _dict_update {dvar args} {
    set name [string map {: {} ( {} ) {}} $dvar]
    upvar 1 $dvar dv
    upvar 1 _my_dict_array$name local

    array set local $dv
    foreach {k v} [lrange $args 0 end-1] {
	if {[info exists local($k)]} {
	    if {![uplevel 1 [list info exists $v]]} {
		uplevel 1 [list upvar 0 _my_dict_array${name}($k) $v]
	    } else {
		uplevel 1 [list set $v $local($k)]
	    }
	}
    }
    set code [catch {uplevel 1 [lindex $args end]} res]

    foreach {k v} [lrange $args 0 end-1] {
	if {[uplevel 1 [list info exists $v]]} {
	    set local($k) [uplevel 1 [list set $v]]
	} else {
	    unset -nocomplain local($k)
	}
    }
    set dv [array get local]
    unset local

    return -code $code $res
}

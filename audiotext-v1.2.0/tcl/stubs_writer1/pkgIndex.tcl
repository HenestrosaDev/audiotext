if {![package vsatisfies [package provide Tcl] 8.4]} {return}
#checker -scope global exclude warnUndefinedVar
package ifneeded stubs::writer 1 [list source [file join $dir writer.tcl]]

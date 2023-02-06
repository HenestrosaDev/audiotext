if {![package vsatisfies [package provide Tcl] 8.4]} {return}
#checker -scope global exclude warnUndefinedVar
package ifneeded stubs::gen::decl 1 [list source [file join $dir gen_decl.tcl]]

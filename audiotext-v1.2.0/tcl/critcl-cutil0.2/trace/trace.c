/*
 * Copyright (c) 2017-2018 Andreas Kupries <andreas_kupries@users.sourceforge.net>
 * = = == === ===== ======== ============= =====================
 */

#include <critcl_alloc.h>
#include <string.h>

/*
 * = = == === ===== ======== ============= =====================
 */

#ifdef CRITCL_TRACER

/* Tracking the stack of scopes,
 * single-linked list,
 * top to bottom.
 */

typedef struct scope_stack {
    const char*         scope;
    struct scope_stack* down;
} scope_stack;

/*
 * = = == === ===== ======== ============= =====================
 * Tracing state (stack of scopes, associated indentation level)
 *
 * API regexp for trace output:
 *  (header printf* closer)*
 *
 * - closed == 1 :: post (closer)
 * - closed == 0 :: post (header)
 *
 * [1] in (header) && !closed
 *     => starting a new line in the middle of an incomplete line
 *     => force closer
 * [2] in (printf) && closed
 *     => continuing a line which was interrupted by another (see [1])
 *     => force header
 */

static scope_stack* top   = 0;
static int          level = 0;
static int          closed = 1;

/*
 * = = == === ===== ======== ============= =====================
 * Internals
 */

static void
indent (void)
{
    int i;
    for (i = 0; i < level; i++) { fwrite(" ", 1, 1, stdout); }
    fflush (stdout);
}

static void
scope (void)
{
    if (!top) return;
    fwrite (top->scope, 1, strlen(top->scope), stdout);
    fflush (stdout);
}

static void
separator (void)
{
    fwrite(" | ", 1, 3, stdout);
    fflush             (stdout);
}

/*
 * = = == === ===== ======== ============= =====================
 * API
 */

void
critcl_trace_push (const char* scope)
{
    scope_stack* new = ALLOC (scope_stack);
    new->scope = scope;
    new->down  = top;
    top = new;
    level += 4;
}

void
critcl_trace_pop (void)
{
    scope_stack* next = top->down;
    level -= 4;
    ckfree ((char*)top);
    top = next;
}

void
critcl_trace_closer (int on)
{
    if (!on) return;
    fwrite ("\n", 1, 1, stdout);
    fflush (stdout);
    closed = 1;
}

void
critcl_trace_header (int on, int ind, const char* filename, int line)
{
    if (!on) return;
    if (!closed) critcl_trace_closer (1);
    // location prefix
#if 0 /* varying path length breaks indenting by call level :( */
    if (filename) {
	fprintf (stdout, "%s:%6d", filename, line);
	fflush  (stdout);
    }
#endif
    // indentation, scope, separator
    if (ind) { indent (); }
    scope ();
    separator();
    closed = 0;
}

void
critcl_trace_printf (int on, const char *format, ...)
{
    /*
     * 1MB output-buffer. We may trace large data structures. This is also a
     * reason why the implementation can be compiled out entirely.
     */
#define MSGMAX (1024*1024)
    static char msg [MSGMAX];
    int len;
    va_list args;
    if (!on) return;
    if (closed) critcl_trace_header (1, 1, 0, 0);

    va_start(args, format);
    len = vsnprintf(msg, MSGMAX, format, args);
    va_end(args);
    fwrite(msg, 1, len, stdout);
    fflush             (stdout);
}

void
critcl_trace_cmd_args (const char* scopename, int argc, Tcl_Obj*const* argv)
{
    int i;
    critcl_trace_push (scopename);
    for (i=0; i < argc; i++) {
	// No location information
	indent();
	scope();
	separator();
	critcl_trace_printf (1, "ARG [%3d] = %p (^%d:%s) '%s'\n",
			     i, argv[i], argv[i]->refCount,
			     argv[i]->typePtr ? argv[i]->typePtr->name : "<unknown>",
			     Tcl_GetString((Tcl_Obj*) argv[i]));
    }
}

int
critcl_trace_cmd_result (int status, Tcl_Interp* ip)
{
    Tcl_Obj*    robj = Tcl_GetObjResult (ip);
    const char* rstr = Tcl_GetString (robj);
    const char* rstate;
    const char* rtype;
    static const char* state_str[] = {
	/* 0 */ "OK",
	/* 1 */ "ERROR",
	/* 2 */ "RETURN",
	/* 3 */ "BREAK",
	/* 4 */ "CONTINUE",
    };
    char buf [TCL_INTEGER_SPACE];
    if (status <= TCL_CONTINUE) {
	rstate = state_str [status];
    } else {
	sprintf (buf, "%d", status);
	rstate = (const char*) buf;
    }
    if (robj->typePtr) {
	rtype = robj->typePtr->name;
    } else {
	rtype = "<unknown>";
    }

    // No location information
    indent();
    scope();
    separator();
    critcl_trace_printf (1, "RESULT = %s %p (^%d:%s) '%s'\n",
			 rstate, robj, robj->refCount, rtype, rstr);
    critcl_trace_pop ();
    return status;
}

#endif /*  CRITCL_TRACER */
/*
 * = = == === ===== ======== ============= =====================
 */

/*
 * local Variables:
 * mode: c
 * c-basic-offset: 4
 * fill-column: 78
 * End:
 */

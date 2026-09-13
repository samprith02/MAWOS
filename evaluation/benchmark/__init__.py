"""Frozen benchmark machinery for MAWOS v3.

Everything in this package was frozen at P0 and is immutable in the sense
that changing it requires a dated entry in evaluation/PROTOCOL.md. The
package exists so that the benchmark stops being a by-product of the
system under test and becomes a fixed instrument pointed at it.

  tasks            query -> gold intent -> gold tool, registry-independent
  distractors      plausible never-correct tools, with a disjointness check
  toolspace        the 5/9/13/20/30 conditions, gold always exposed
  instrumentation  per-trial record keeping "could not" apart from "did not"
"""

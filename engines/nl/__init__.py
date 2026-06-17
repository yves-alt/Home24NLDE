"""Home24.nl deterministic localization engine.

A controlled DE→NL pipeline that never silently fails: terminology and
translation memory do the heavy lifting, GPT (gpt-4o) only refines, and a
quality gate blocks export whenever German residue, lost data, or a changed
model name slips through.
"""

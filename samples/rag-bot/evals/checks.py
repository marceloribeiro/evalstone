"""Checks specific to the support bot, registered with @check."""

from evalstone import check


@check("no_apology")
def no_apology(sample, output):
    """The bot must answer, not apologise."""
    return "sorry" not in output.text.lower()


@check("one_sentence")
def one_sentence(sample, output):
    """Answers are one sentence (this bot's contract)."""
    return output.text.count(". ") == 0

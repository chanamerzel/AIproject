"""MCP stdio server — two Studio tools. Tool names = function names."""

from mcp.server.fastmcp import FastMCP

from mcp_studio.evaluate_requirement_coverage import (
    evaluate_requirement_coverage as coverage_impl,
)
from mcp_studio.extract_resume_profile import extract_resume_profile as extract_impl

mcp = FastMCP("fitscreen-studio")


@mcp.tool()
def extract_resume_profile(cv_text: str) -> dict:
    """Parse a CV into emails, skills, years, last company, and a short summary."""
    return extract_impl(cv_text)


@mcp.tool()
def evaluate_requirement_coverage(
    must_have_skills: str,
    cv_text: str,
    nice_to_have_skills: str = "",
    min_years: int = 0,
    years_experience: int | None = None,
) -> dict:
    """Score how well a CV covers a job's must-have and nice-to-have skills."""
    return coverage_impl(
        must_have_skills,
        nice_to_have_skills,
        cv_text,
        min_years,
        years_experience,
    )


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

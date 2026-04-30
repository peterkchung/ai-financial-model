# FTC v. Amazon (Case 2:23-cv-01495, W.D. Wash.)

Status: NOT YET DOWNLOADED. CourtListener's REST API requires registration
for both search and docket endpoints — anonymous access is denied.

To populate this directory:
1. Register for a free CourtListener account at https://www.courtlistener.com
2. Set CL_API_TOKEN env var
3. Use the docket-id endpoint:
   curl -H "Authorization: Token $CL_API_TOKEN" \
     "https://www.courtlistener.com/api/rest/v3/dockets/?docket_number=2:23-cv-01495"

Alternative free sources:
- FTC press releases: https://www.ftc.gov/news-events/news/press-releases
- Reuters / WSJ docket coverage (not machine-readable but indexed)

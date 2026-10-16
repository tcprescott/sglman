### Fixed

- Discord IDs from the API and the MCP connector come back as text now, so tools written in JavaScript stop rounding off their last digits (320395696098377729 used to read as 320395696098377700). Anything that sends an ID in can still send it as a number.

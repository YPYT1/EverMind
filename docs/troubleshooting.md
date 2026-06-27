# Troubleshooting

## Port 3378 is not listening

Start EverOS and confirm `http://127.0.0.1:3378/health` responds.

## MCP tool times out

Check that the MCP snippet points to the correct `mcp` directory and that `uv` is available.

## Basic Memory notes are not written

Official notes require explicit confirmation. First check the candidate directory.

## Agent does not see new skills

Restart the client or open a new session. Some clients cache skill metadata.



#!/bin/bash
# Complex sourcing patterns that the old line-anchored regex would MISS.
# This file exercises the new tokenizer-based extractor.

# 1. source inside if/then block (was missed by ^\s*source)
if [ -f ./lib/config.sh ]; then
    source ./lib/config.sh
fi

# 2. source with leading environment variable assignment (was missed)
DEBUG=1 VERBOSE=1 source ./lib/utils.sh

# 3. inline multi-command: command then source on same logical line
echo "loading"; source ./lib/config.sh

# 4. source in a conditional && chain
[ -r ./lib/utils.sh ] && source ./lib/utils.sh

# 5. source via the dot builtin after a control keyword
for mod in config; do source ./lib/${mod}.sh; done

# 6. source with command substitution argument (dynamic)
source "$(dirname "$0")/lib/utils.sh"

# 7. plain source for baseline
source ./lib/utils.sh

# 8. dot command after env var
ROOT_DIR=. . ./lib/config.sh

# 9. source inside a subshell-style brace group
{ source ./lib/utils.sh; }

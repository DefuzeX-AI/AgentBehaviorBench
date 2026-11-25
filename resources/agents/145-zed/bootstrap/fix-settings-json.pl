use strict;
use warnings;

# Honor the upstream contribution marker in the disposable source tree.
{
    open my $readme_input, '<', 'README.md' or die $!;
    local $/;
    my $readme = <$readme_input>;
    close $readme_input;
    my $marker = "> [!IMPORTANT]\n> Remove this line to confirm you've reviewed this PR before submitting.\n";
    if (index($readme, $marker) != 0) {
        open my $readme_output, '>', 'README.md' or die $!;
        print {$readme_output} $marker, $readme;
        close $readme_output;
    }
}

# Pinned upstream eval-cli adds a literal quote after its settings JSON object.
# Apply only to the disposable build copy, and fail on unexpected source drift.
my $path = 'crates/eval_cli/src/main.rs';
open my $input, '<', $path or die "$path: $!";
local $/;
my $source = <$input>;
close $input;
my $count = ($source =~ s/(                    "format_on_save": "off"\r?\n                }})"/$1/g);
die "Expected exactly one pinned settings JSON defect, found $count" unless $count == 1;
open my $output, '>', $path or die "$path: $!";
print {$output} $source;
close $output;

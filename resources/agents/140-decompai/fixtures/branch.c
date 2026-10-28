#include <stdio.h>
int classify(int value) { return value > 7 ? 42 : -3; }
int main(void) { puts("DecompAI ABB fixture"); return classify(8) == 42 ? 0 : 1; }

{
  inputs = { };
  outputs = inputs@{ self, ... }: { dirs = [ "./." ./. (toString ./.) ]; };
}

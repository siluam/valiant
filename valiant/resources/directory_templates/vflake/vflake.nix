{
  inputs = { };
  outputs = inputs@{ self, ... }: {
    dirs = [ "../xml" ];
    valiant = true;
  };
}

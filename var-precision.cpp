class ir_variable : public ir_instruction {
   /* … */
public:
   struct ir_variable_data {
      /* … */
      /**
       * Precision qualifier.
       *
       * In desktop GLSL we do not care about precision qualifiers at
       * all, in fact, the spec says that precision qualifiers are
       * ignored.
       *
       * To make things easy, we make it so that this field is always
       * GLSL_PRECISION_NONE on desktop shaders. This way all the
       * variables have the same precision value and the checks we add
       * in the compiler for this field will never break a desktop
       * shader compile.
       */
      unsigned precision:2;
      /* … */
   };
};

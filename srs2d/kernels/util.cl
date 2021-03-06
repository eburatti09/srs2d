#ifndef __UTIL_CL__
#define __UTIL_CL__

float2 rot_mul_vec(rotation_t r, float2 v)
{
    float2 res = { r.cos * v.x - r.sin * v.y,
                   r.sin * v.x + r.cos * v.y };
    return res;
}

float2 transform_mul_vec(transform_t t, float2 v)
{
    float2 res = { (t.rot.cos * v.x - t.rot.sin * v.y) + t.pos.x,
                   (t.rot.sin * v.x + t.rot.cos * v.y) + t.pos.y };
    return res;
}

float angle(float sin, float cos) {
    float a = atan2(sin, cos);
    if (a < 0) return a + 2*M_PI;
    return a;
}

float angle_rot(rotation_t rot) {
    return angle(rot.sin, rot.cos);
}

unsigned int uint_exp2(unsigned int n)
{

    return floor(exp2((float) n));
}

float sigmoid(float z)
{
    return 1 / (1 + exp(-z));
}

float scale_param(float p, float boundary_l, float boundary_h)
{
    return p * (boundary_h - boundary_l) + boundary_l;
}

#endif
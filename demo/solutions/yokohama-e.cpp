#include<bits/stdc++.h>
using namespace std;
typedef long long ll;

ll gcdll(ll a,ll b)
{
    return b?gcdll(b,a%b):a;
}

bool enough(const array<ll,3>& side,ll p,ll q,ll k)
{
    ll count=1;
    for(ll x:side)
    {
        ll along=x*q/p;
        // Both factors are capped at k, so the product fits in 64 bits.
        count=min(k,count*min(k,along));
    }
    return count>=k;
}

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int t;
    if(!(cin>>t)) return 0;
    while(t--)
    {
        array<ll,3> side;
        ll k,p=0,q=1;
        cin>>side[0]>>side[1]>>side[2]>>k;
        // At the optimum, some axis fits a whole number of cubes exactly.
        for(ll x:side)
        {
            ll l=1,r=max(x,k);
            // At q=r, side length x/r<=1 and the x-axis alone fits r>=k.
            while(l<r)
            {
                ll mid=l+(r-l)/2;
                if(enough(side,x,mid,k)) r=mid;
                else l=mid+1;
            }
            if(x*q>p*l) p=x,q=l;
        }
        ll g=gcdll(p,q);
        cout<<p/g<<' '<<q/g<<'\n';
    }
    return 0;
}

#include<bits/stdc++.h>
using namespace std;
using ll=long long;

struct Line
{
    int j;
    ll b;
    ll at(ll x) const {return j*x+b;}
};

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n,m;
    cin>>n>>m;
    vector<ll> a(n+2),s(n+3),delay(n+1),ans(m);
    for(int i=1;i<=n;i++)
    {
        cin>>a[i];
        // Maximum days spent in this prefix: isolate nonadjacent wheat plots.
        delay[i]=max(delay[i-1],a[i]+(i>1?delay[i-2]:0));
    }
    for(int i=n;i;i--) s[i]=s[i+1]+a[i];
    vector<vector<pair<int,ll>>> ask(n+1);
    for(int q=0;q<m;q++)
    {
        ll d;
        cin>>d;
        int k=lower_bound(delay.begin(),delay.end(),d)-delay.begin();
        if(k>n) continue;
        // k is the first prefix which could occupy the boar for d days.
        // Clearing k+1 shields the entire suffix starting at k+2.
        ans[q]=s[k+2];
        for(int i=max(1,k);i<=min(n,k+1);i++)
            ask[i].push_back({q,d-(i>1?delay[i-2]:0)});
    }
    vector<Line> hull;
    for(int i=n;i;i--)
    {
        // Clear j>i (j=n+1 means no barrier). Loss in the suffix is
        // a[j]+(j-i)*t. Lower lines support all possible final barriers.
        Line f={i+1,a[i+1]};
        while(hull.size()>=2)
        {
            Line x=hull[hull.size()-2],y=hull.back();
            if((y.b-x.b)*(y.j-f.j)<(f.b-y.b)*(x.j-y.j)) break;
            hull.pop_back();
        }
        hull.push_back(f);
        for(auto q:ask[i])
        {
            ll t=q.second; // delay[k] first reached d; t never exceeds a[k].
            int l=0,r=(int)hull.size()-1;
            while(l<r)
            {
                int mid=(l+r)/2;
                if(hull[mid].at(t)<=hull[mid+1].at(t)) r=mid;
                else l=mid+1;
            }
            ans[q.first]=max(ans[q.first],s[i]+i*t-hull[l].at(t));
        }
    }
    for(ll v:ans) cout<<v<<'\n';
    return 0;
}

#include<bits/stdc++.h>
using namespace std;
int n;
signed main()
{
    ios::sync_with_stdio(0),cin.tie(0),cout.tie(0);
    int T;
    cin>>T;
    while(T--)
    {
        vector<int> res;
        cin>>n;
        vector<int> a;
        while(n)
        {
            a.push_back(n%10);
            n/=10;
        }
        int fact=1;
        for(int i=0;i<a.size();i++)
        {
            if(a[i]!=0) res.push_back(a[i]*fact);
            fact*=10;
        }
        cout<<res.size()<<endl;
        for(auto t:res) cout<<t<<' ';
        cout<<endl;
    }
    return 0;
}